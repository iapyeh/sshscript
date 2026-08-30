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

import threading, os,sys

import time,random
import subprocess
import selectors
import errno
import asyncio
import fcntl
import signal
if __package__:
    from .channelgeneric import GenericChannel
    from .errorutils import EXITCODE_DEFAULT,get_logger
else:
    from channelgeneric import GenericChannel
    from errorutils import EXITCODE_DEFAULT,get_logger

logger = get_logger()

class POpenChannel(GenericChannel):
    """Channel implementation for subprocess communication using POpen.
    
    Handles communication with subprocesses through standard input/output streams
    and PTY operations.
    """
    count = 0
    def __init__(self,owner,cp,stdouterr,stdin,pty_to_close:list,get_pty:bool):
        """Initialize POpenChannel.
        
        :stdouterr:(list)
            [0]: stdout to read
            [1]: stderr to read
        :pty_to_close:(list)
            file handle to close when this channel.close() was called
        :get_pty:
            owner (Dollar()) hints if this channel is a pty channel
            doesn't matter if there is no cp (instance of subprocess.Popen)
        """
        super(POpenChannel,self).__init__(owner)
        self.prefixOfLog = "[POpen]"
        self.get_pty = get_pty
        self.cp = cp
        self.stdouterr = stdouterr
        self.stdin = stdin
        self._pty_to_close = pty_to_close
        self._reading_thread = None
        #if self.cp:
        #    assert isinstance(self.stdouterr,list) and len(self.stdouterr)==2, f'standard output and error should be in a list of 2 elements, but got {self.stdouterr}'
        #    #self._dumpThread.start()
        if self.cp:
            assert isinstance(self.stdouterr, list)
            if self.get_pty:
                assert len(self.stdouterr) == 1, (
                    'PTY channel must have exactly one merged output descriptor, '
                    f'got {self.stdouterr}'
                )
            else:
                assert len(self.stdouterr) == 2, (
                    'non-PTY channel must have stdout and stderr descriptors, '
                    f'got {self.stdouterr}'
                )            
    async def _start_reading(self):  
        #asyncio.create_task(self._dumpThread.start())
        assert self.cp is not None 
        
        ## important for getting correct value of command output, can not be slow
        interval = 0.01

        if self.get_pty:
            ## 2025/05/12, when get_pty is True, stdout and stdin were mixed
            #async def _reading():
            #    flags = fcntl.fcntl(self.stdouterr[0], fcntl.F_GETFL)
            #    fcntl.fcntl(self.stdouterr[0], fcntl.F_SETFL, flags | os.O_NONBLOCK)
            #    flags = fcntl.fcntl(self.stdouterr[1], fcntl.F_GETFL)
            #    #fcntl.fcntl(self.stdouterr[1], fcntl.F_SETFL, flags | os.O_NONBLOCK)
            #    try:
            #        ## reads pty
            #        sel = selectors.DefaultSelector()
            #        sel.register(self.stdouterr[0], selectors.EVENT_READ, data="stdout")
            #        sel.register(self.stdouterr[1], selectors.EVENT_READ, data="stderr")
            #        while self.cp.poll() is None:
            #            events = sel.select(timeout=0.1)
            #            for key, mask in events:
            #                # key.fileobj 是原始的 pipe 物件
            #                # key.data 是我們剛才註冊的自定義字串
            #                data = os.read(key.fileobj,1024)
            #                await callback[key.fileobj](data)
            #            await asyncio.sleep(interval)
            #            
            #    except OSError as e:
            #        ## when subprocess exited, the file descriptor would be closed, and os.read() would raise OSError with errno.EIO 
            #        ## on Ubuntu and Macos, but not on Windows    
            #        if e.errno != errno.EIO:
            #            raise
            #    except asyncio.exceptions.CancelledError:
            #        raise
            #    finally:
            #        sel.close()

            ##2026/8/5 by codex
            async def _reading():
                masterFd = self.stdouterr[0]

                flags = fcntl.fcntl(masterFd, fcntl.F_GETFL)
                fcntl.fcntl(
                    masterFd,
                    fcntl.F_SETFL,
                    flags | os.O_NONBLOCK,
                )

                sel = selectors.DefaultSelector()

                try:
                    sel.register(
                        masterFd,
                        selectors.EVENT_READ,
                        data='stdout',
                    )

                    while True:
                        events = sel.select(timeout=0.1)

                        for key, mask in events:
                            try:
                                data = os.read(key.fileobj, 65536)
                            except BlockingIOError:
                                continue
                            except OSError as exc:
                                # PTY slave 全部關閉後，master 通常以 EIO 表示 EOF。
                                if exc.errno == errno.EIO:
                                    return

                                # close() 可能已關閉 master。
                                if (
                                    exc.errno == errno.EBADF
                                    and (
                                        self.closed
                                        or self.cp.poll() is not None
                                    )
                                ):
                                    return

                                raise

                            if not data:
                                return

                            # PTY 的 stdout/stderr 是合併資料。
                            await self._add_stdout_data(data)

                        # Process 已結束且沒有剩餘可讀資料。
                        if self.cp.poll() is not None and not events:
                            break

                        await asyncio.sleep(interval)

                except asyncio.CancelledError:
                    raise
                finally:
                    sel.close()

        else:
            callback = {
                self.stdouterr[0]: self._add_stdout_data,
                self.stdouterr[1]: self._add_stderr_data
            }            
            async def _reading():
                try:
                    ## reads without pty (e.g. subprocess.PIPE)
                    sel = selectors.DefaultSelector()
                    sel.register(self.stdouterr[0], selectors.EVENT_READ, data="stdout")
                    sel.register(self.stdouterr[1], selectors.EVENT_READ, data="stderr")

                    while self.cp.poll() is None:
                        """
                        for fd in select(stream, [], [],interval)[0]:
                            callback[fd](os.read(fd,1024))
                        """
                        events = sel.select(timeout=0.1)
                        for key, mask in events:
                            # key.fileobj 是原始的 pipe 物件
                            # key.data 是我們剛才註冊的自定義字串
                            await callback[key.fileobj](os.read(key.fileobj,1024))
                        await asyncio.sleep(interval)
                except OSError as e:
                    ## when subprocess exited, the file descriptor would be closed, and os.read() would raise OSError with errno.EIO 
                    ## on Ubuntu and Macos, but not on Windows    
                    if e.errno != errno.EIO:
                        raise
                finally:
                    sel.close()
        POpenChannel.count += 1
        await _reading()
        logger.debug(
            '[POpen] Subprocess reader stopped (pid=%s, returncode=%s)',
            self.cp.pid,
            self.cp.poll(),
        )

    def raw_send(self,s):
        """Send data to subprocess through stdin.
        
        :s: string to send
        """
        if self.closed or self.cp.poll() is not None:
            raise BrokenPipeError(
                errno.EPIPE,
                f'Subprocess channel is closed (pid={self.cp.pid})',
            )
        try:
            os.write(self.stdin,s.encode('utf-8'))
            ## would raise OSError on Ubuntu and Macos
            try:
                os.fsync(self.stdin)
            except OSError:
                pass
        except OSError:
            raise
        finally:
            self.touchIO(False)

    def current_pid(self):
        """ for debuging only"""
        def get_child_pid(ppid):
            try:
                children = subprocess.check_output(['pgrep', '-P', str(ppid)]).decode().strip()
                if children:
                    return get_child_pid(int(children.split()[0]))  # first child
                else:
                    return ppid
            except subprocess.CalledProcessError:
                ## no child process found, return the current ppid
                return ppid
        return get_child_pid(self.cp.pid)
    def close(self):
        """Close channel and cleanup resources.
        
        Sends exit command, waits for subprocess to exit, and closes PTY handles.
        """
        if not self._begin_close():
            return

        try:
            if self.cp:
                pid = self.cp.pid
                if self.cp.poll() is None:
                    timeout = 2
                    logger.debug(
                        '[POpen] Waiting for subprocess to exit (pid=%s, timeout=%ss)',
                        pid,
                        timeout,
                    )
                    try:
                        self.cp.wait(timeout)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            '[POpen] Subprocess did not exit before close timeout; '
                            'terminating (pid=%s, timeout=%ss)',
                            pid,
                            timeout,
                        )
                        self.cp.terminate()
                        try:
                            self.cp.wait(timeout)
                        except subprocess.TimeoutExpired:
                            logger.warning(
                                '[POpen] Subprocess did not terminate before timeout; '
                                'killing (pid=%s, timeout=%ss)',
                                pid,
                                timeout,
                            )
                            self.cp.kill()
                            self.cp.wait(timeout)

                if self._exitcode in (None, EXITCODE_DEFAULT):
                    self._exitcode = self.cp.poll()
                ## close the pty
                for fd in self._pty_to_close:
                    if isinstance(fd,int):
                        os.close(fd)
                    else:
                        fd.close()

                logger.debug(
                    '[POpen] Subprocess channel closed (pid=%s, returncode=%s)',
                    pid,
                    self.cp.poll(),
                )
        finally:
            ## close the i/o of local buffers
            self._finish_close()