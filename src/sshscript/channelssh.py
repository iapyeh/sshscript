# Copyright (C) 2022-2026  Hsin Yuan Yeh <iapyeh@gmail.com>
#
# This file is part of Sshscript.
#
# SSHScript is free software; you can redistribute it and/or modify it under the
# terms of the MIT License.
#
# SSHScript is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the MIT License for more details.
#
# You should have received a copy of the MIT License along with SSHScript;
# if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA.
#
import errno
import os
import paramiko
from paramiko.ssh_exception import SSHException
import time
#from select import select
import selectors
import asyncio
if __package__:
    from .channelgeneric import GenericChannel
    from .errorutils import get_logger
else:
    from channelgeneric import GenericChannel
    from errorutils import get_logger
logger = get_logger()
class ParamikoChannel(object):
    """Helper class for SSHChannel to manage PTY and non-PTY SSH sessions.
    
    This class handles the low-level communication with SSH channels using Paramiko,
    supporting both PTY and non-PTY modes for different use cases.
    """
    count = 0
    def __init__(self,sshchannel,get_pty,channel=None):
        """Initialize ParamikoChannel.
        
        :sshchannel: parent SSHChannel instance
        :get_pty: whether to enable PTY mode
        """
        assert isinstance(sshchannel, SSHChannel)
        self.sshchannel = sshchannel 
        self.get_pty = get_pty
        self.suspending = False
        if channel is None:
            self.channel = sshchannel.client.get_transport().open_session()
            ## Note: for environment variable to work,
            ##      /etc/ssh/sshd_config should permit "LC*" environment to be set
            # Never forward the caller's complete process environment.  It may
            # contain API tokens, cloud credentials, or CI secrets.  Interactive
            # SSH sessions receive only terminal/locale defaults plus values the
            # caller explicitly supplied through ``env=``.
            environment = {
                'TERM': 'dumb',
                'LC_ALL': 'en_US.UTF-8',
                'LANG': 'en_US.UTF-8',
            }
            requested_environment = getattr(
                sshchannel.owner,
                '_parameters_to_execute',
                {},
            ).get('environment', {})
            if requested_environment:
                environment.update(requested_environment)
            self.channel.update_environment(environment)
            if self.get_pty:
                ## should enable pty, because without it, interactive python, mysql client won't work.
                ## but it also produce "prompt" into stdout. that is a problem.
                ## 2025/3/7, set default term to "dumb"
                self.channel.get_pty('dumb')
            else:
                ## twodollars, no pty support
                self.channel.set_combine_stderr(False)
        else:
            ## two dollars
            self.channel = channel
        
        ## v2.0.3起不設定為 commandTimeout
        ## 這是paramiko的socket timeout 時間，不是指令結束時間
        #self.channel.settimeout(self.commandTimeout)
        
        ## two-dollars has no self.command
        if self.sshchannel.owner.command:
            logger.debug(
                '[SSHChannel] Executing remote command (host=%s, pty=%s)',
                self.sshchannel.owner.session.host,
                self.get_pty,
            )
            self.channel.exec_command(self.sshchannel.owner.command)

        ParamikoChannel.count += 1
        #threading.Thread(target=self._reading,name=f'ssh{ParamikoChannel.count}',daemon=True,no_patch=True).start()

        ## wait for message of today, prompt of the shell
        self.sshchannel.wait_for_silent(0.25)

    async def _start_reading(self):         
        async def _reading():
            """Background thread for reading from SSH channel.
            
            Reads from stdout/stderr and adds data to parent channel buffers.
            """
            ## this runs in a thread
            stdout = self.channel.makefile()
            stderr = self.channel.makefile_stderr()
            ## by checking self.closed, "exit" would not be put into stdout
            sel = selectors.DefaultSelector()
            sel.register(self.channel, selectors.EVENT_READ, data="stdout")
            try:
                while not (self.channel.closed or self.channel.exit_status_ready()):
                    if self.suspending:
                        await asyncio.sleep(1)
                        continue            
                    events = sel.select(timeout=0.1)
                    if len(events):
                        #for key, mask in events:
                        # key.fileobj 是原始的 pipe 物件
                        # key.data 是我們剛才註冊的自定義字串
                        try:
                            while self.channel.recv_ready():
                                await self.sshchannel._add_stdout_data(stdout._read(1024)) 
                            while self.channel.recv_stderr_ready():
                                await self.sshchannel._add_stderr_data(stderr._read(1024))
                        except (SSHException,ValueError):
                            if self.channel.closed or self.channel.exit_status_ready():
                                break
                            logger.exception(
                                '[SSHChannel] SSH channel read failed (host=%s)',
                                self.sshchannel.owner.session.host,
                            )
                            raise
                    await asyncio.sleep(0.1)
            except OSError as e:
                if e.errno != errno.EIO and not self.channel.closed:
                    logger.exception(
                        '[SSHChannel] SSH channel reader failed (host=%s)',
                        self.sshchannel.owner.session.host,
                    )
                    raise
            except asyncio.exceptions.CancelledError:
                raise
            finally:
                sel.close()
            ## some command (eg. $.enter('mariadb -uroot -p myrpki < /tmp/test.sql')) would auto close the channel,
            ## so we need to close the sshchannel too
            #if not self.sshchannel.closed:
            #    self.sshchannel.close()
        await _reading()
    def raw_send(self,s):
        """Send data through SSH channel.
        
        :s: string to send
        """
        if self.channel.closed:
            raise BrokenPipeError(
                errno.EPIPE,
                f'SSH channel is closed (host={self.sshchannel.owner.session.host})',
            )
        self.channel.sendall(s)
    
    def exit_status_ready(self):
        """Check if channel exit status is ready.
        
        :return: True if exit status available
        """
        return self.channel.exit_status_ready()
    
    def recv_exit_status(self):
        """Get channel exit status.
        
        :return: exit status code
        """
        return self.channel.recv_exit_status()

    def shutdown_write(self):
        """Shutdown write side of channel.
        
        :return: result of channel shutdown_write
        """
        return self.channel.shutdown_write()


    def close(self):
        """Close SSH channel and cleanup.
        
        Sends exit command, waits for closure, handles errors.
        """
        host = self.sshchannel.owner.session.host
        logger.debug('[SSHChannel] Closing SSH channel (host=%s)', host)
        ## automatically send exit to shell
        try:
            if not self.channel.exit_status_ready():
                self.channel.shutdown_write()            
            ## wait for exit_status_ready()
            timeout_seconds = 20
            deadline = time.monotonic() + timeout_seconds
            while True:
                if time.monotonic() > deadline:
                    logger.warning(
                        '[SSHChannel] Exit status was not received before close timeout; '
                        'forcing channel close (host=%s, timeout=%ss)',
                        host,
                        timeout_seconds,
                    )
                    break
                elif self.channel.exit_status_ready():
                    ## don't override _exitcode with channel's exitcode
                    ## keep it to be the exitcode of last command
                    #self.sshchannel._exitcode = self.channel.recv_exit_status()
                    break
                else:
                    time.sleep(0.1)
        except (SSHException, OSError):
            logger.exception('[SSHChannel] Failed to close SSH channel (host=%s)', host)
            raise
        finally:
            self.channel.close()
    
class SSHChannel(GenericChannel):
    """Channel implementation for SSH communication.
    
    Manages SSH sessions with PTY and non-PTY modes.
    """
    is_ssh_channel = True

    def __init__(self,owner,client,get_pty=False):
        """Initialize SSHChannel.
        
        :owner: channel owner
        :client: SSH client instance
        :get_pty: whether to enable PTY mode (default: True)
        """
        super().__init__(owner)
        self.get_pty = get_pty
        with self.executing_lock:
            assert not self.closed
            self.prefixOfLog = "[SSHChannel]"
           
            if isinstance(client,paramiko.client.SSHClient):
                ## paramiko's invoke_shell
                self.client = client
                #self._dumpThread.start()
                self.channel = ParamikoChannel(self,get_pty)
                if self.get_pty:
                    ## help to remove garbage from stdout or stderr
                    ## this is helpful for  ssh 's shell 
                    ## may not work for "dash"
                    #self.input('stty -echo')
                    #self.wait_for_silent(0.25)
                    #self.reset_buffer()
                    pass
            elif isinstance(client,paramiko.channel.Channel):
                ## paramiko's invoke_shell
                self.client = None
                #self._dumpThread.start()
                self.channel = ParamikoChannel(self,get_pty,channel=client)
                if self.get_pty:
                    ## help to remove garbage from stdout or stderr
                    ## this is helpful for  ssh 's shell 
                    ## may not work for "dash"
                    #self.input('stty -echo')
                    #self.wait_for_silent(0.25)
                    #self.reset_buffer()
                    pass
            else:
                ## dummy channel
                self.client = None
                self.channel = None
        
    def raw_send(self,s):
        """Send data through SSH channel.
        
        :s: string to send
        """
        try:
            self.channel.raw_send(s)
        finally:
            self.touchIO(False)
    
    async def _start_reading(self):
        await self.channel._start_reading()

    '''
    def close(self):
        """Close SSH channel and cleanup.
        
        Closes main channel and any cached PTY/non-PTY channels.
        """
        ## close the i/o of remote server
        #while self.sending_queue.qsize() > 0:
        #    time.sleep(0.1)
        if self.channel:
            if not self.channel.channel.closed:
                self.channel.close()
            self._exitcode = self.channel.recv_exit_status()
        ## close the i/o of local buffers
        super().close()
    '''
    def close(self):
        if not self._begin_close():
            return

        channel = self.channel

        try:
            if channel is not None:
                try:
                    if not channel.channel.closed:
                        # ParamikoChannel.close() 已有 20 秒上限。
                        channel.close()
                finally:
                    # recv_exit_status() 只能在 ready 時呼叫。
                    if channel.exit_status_ready():
                        self._exitcode = (
                            channel.recv_exit_status()
                        )
        finally:
            # 即使 Paramiko cleanup raise，也要關閉本地 buffer，
            # 並讓其他 waiter 看到 closed。
            self._finish_close()
