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
import __main__
import threading, os, logging
import paramiko
from paramiko.ssh_exception import SSHException
import tty
import time
from select import select

try:
    from .channelgeneric import GenericChannel
    from .errorutils import log_debug_8,EXITCODE_DEFAULT,logger
except ImportError:
    from channelgeneric import GenericChannel
    from errorutils import log_debug_8,EXITCODE_DEFAULT,logger

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
            self.channel.update_environment(dict(os.environ,TERM='dumb',LC_ALL='en_US.UTF-8',LANG='en_US.UTF-8'))
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
            log_debug_8(f'[ParamikoChannel] runs {self.sshchannel.owner.command}')
            self.channel.exec_command(self.sshchannel.owner.command)

        ParamikoChannel.count += 1
        threading.Thread(target=self._reading,name=f'ssh{ParamikoChannel.count}',daemon=True,no_patch=True).start()

        if self.sshchannel.owner.inWith:
            ## wait for message of today, prompt of the shell
            self.sshchannel.wait_for_silent(0.25)
        else:
            ## twodollars
            self.sshchannel.wait_for_silent(0.25)    

    def _reading(self):
        """Background thread for reading from SSH channel.
        
        Reads from stdout/stderr and adds data to parent channel buffers.
        """
        ## this runs in a thread
        stdout = self.channel.makefile()
        stderr = self.channel.makefile_stderr()
        ## by checking self.closed, "exit" would not be put into stdout
        while True:
            if self.suspending:
                time.sleep(1)
                continue            
            elif (self.channel.closed or self.channel.exit_status_ready()):
                break
            else:
                try:
                    if select([self.channel],[],[],0.25)[0]:
                        try:
                            while self.channel.recv_ready():
                                self.sshchannel._add_stdout_data(stdout._read(1024))     
                            while self.channel.recv_stderr_ready():
                                self.sshchannel._add_stderr_data(stderr._read(1024))
                        except (SSHException,ValueError) as e:
                            self.sshchannel.log(f'{id(self)}, closed={self.sshchannel.closed}, Error on reading:{e}')
                            break 
                except OSError as e:
                    log_debug_8(str(e))
        ## some command (eg. $.enter('mariadb -uroot -p myrpki < /tmp/test.sql')) would auto close the channel,
        ## so we need to close the sshchannel too
        #if not self.sshchannel.closed:
        #    self.sshchannel.close()
    def send(self,s):
        """Send data through SSH channel.
        
        :s: string to send
        """
        if self.channel.closed:
            logger.error(f'{self.sshchannel.owner.session.host} channel is closed, can not send "{s}"')
            return
        self.sshchannel.log8(f'[{self.sshchannel.owner.session.host}] send->{[s]}')
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
        self.sshchannel.log(f'[{self.sshchannel.owner.session.host}] closing ssh channel')
        ## automatically send exit to shell
        try:
            if not self.channel.exit_status_ready():
                self.send('exit\n')                
                self.channel.shutdown_write()
            
            timeout = time.time() + 20
            while True:
                if time.time() > timeout:
                    self.sshchannel.log(f'[{self.sshchannel.owner.session.host}] forced to close, no exitcode received')
                    break
                elif self.channel.exit_status_ready():
                    ## don't override _exitcode with channel's exitcode
                    ## keep it to be the exitcode of last command
                    #self.sshchannel._exitcode = self.channel.recv_exit_status()
                    break
                else:
                    time.sleep(0.1)
            self.channel.close()
        except paramiko.ssh_exception.SSHException as e:
            self.sshchannel.log(f'[{self.sshchannel.owner.session.host}] error on closing:{e}')
            raise
        except OSError as e:
            self.sshchannel.log(f'[{self.sshchannel.owner.session.host}] error on closing:{e}')
            raise
        return self.channel.close()

class SSHChannel(GenericChannel):
    """Channel implementation for SSH communication.
    
    Manages SSH sessions with PTY and non-PTY modes.
    """
    def __init__(self,owner,client,get_pty=False):
        """Initialize SSHChannel.
        
        :owner: channel owner
        :client: SSH client instance
        :get_pty: whether to enable PTY mode (default: True)
        """
        super(SSHChannel,self).__init__(owner)
        self.get_pty = get_pty
        with self.executing_lock:
            assert not self.closed
            self.prefixOfLog = "[SSHChannel]"
           
            if isinstance(client,paramiko.client.SSHClient):
                ## paramiko's invoke_shell
                self.client = client
                self._dumpThread.start()
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
                self._dumpThread.start()
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
        
    def send(self,s):
        """Send data through SSH channel.
        
        :s: string to send
        """
        self.channel.send(s)
        self.touchIO(False)

    def close(self):
        """Close SSH channel and cleanup.
        
        Closes main channel and any cached PTY/non-PTY channels.
        """
        ## close the i/o of remote server
        if self.channel and not self.channel.channel.closed:
            if self._exitcode == EXITCODE_DEFAULT:
                ## The last command's exitcode not yet been retrieved.
                ## We have to call it before closing the channel. In case like this:
                ## with $.sudo():
                ##       ... without calling getExitcode() ...
                ## print($.exitcode) <== here, would raise "OSError: [Errno 9] Bad file descriptor", since file has closed
                self._exitcode = self.channel.recv_exit_status()

            self.channel.close()
        ## close the i/o of local buffers
        super().close()

__main__.SSHChannel = SSHChannel