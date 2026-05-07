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
try:
    from .channelgeneric import GenericChannel
    from .errorutils import EXITCODE_DEFAULT
except ImportError:
    from channelgeneric import GenericChannel
    from errorutils import EXITCODE_DEFAULT

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
        if self.cp:
            assert isinstance(self.stdouterr,list) and len(self.stdouterr)==2, f'standard output and error should be in a list of 2 elements, but got {self.stdouterr}'
            #self._dumpThread.start()
    async def _start_reading(self):  
        #asyncio.create_task(self._dumpThread.start())
        assert self.cp is not None 
        
        ## important for getting correct value of command output, can not be slow
        interval = 0.01
        callback = {
            self.stdouterr[0]: self._add_stdout_data,
            self.stdouterr[1]: self._add_stderr_data
        }
        if self.get_pty:
            ## 2025/05/12, when get_pty is True, stdout and stdin were mixed
            async def _reading():
                try:
                    ## reads pty
                    sel = selectors.DefaultSelector()
                    sel.register(self.stdouterr[0], selectors.EVENT_READ, data="stdout")
                    sel.register(self.stdouterr[1], selectors.EVENT_READ, data="stderr")
                    while self.cp.poll() is None:
                        events = sel.select(timeout=0.1)
                        for key, mask in events:
                            # key.fileobj 是原始的 pipe 物件
                            # key.data 是我們剛才註冊的自定義字串
                            await callback[key.fileobj](os.read(key.fileobj,1024))          
                        await asyncio.sleep(interval)
                    
                except asyncio.exceptions.CancelledError:
                    pass
                finally:
                    sel.close()
        else:
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
                finally:
                    sel.close()
        POpenChannel.count += 1
        await _reading()

    def raw_send(self,s):
        """Send data to subprocess through stdin.
        
        :s: string to send
        """
        self.log8(f'send->{[s]}')
        assert not self.closed and self.cp.poll() is None, f'subprocess {self.cp} has closed,closed={self.closed}, poll={self.cp.poll()}'
        
        try:
            os.write(self.stdin,s.encode('utf-8'))
            ## would raise OSError on Ubuntu and Macos
            #os.fsync(self.stdin)
        except OSError as e:
            self.log(f'{self.cp}: OSError on writing; {e}')
            raise
        finally:
            self.touchIO(False)
    
    def close(self):
        """Close channel and cleanup resources.
        
        Sends exit command, waits for subprocess to exit, and closes PTY handles.
        """
        
        if self.cp:
            if self.cp.poll() is None:
                self.log(f'Waiting for subprocess to exit...')
                while self.cp.poll() is None:                
                    time.sleep(0.1)

            ## 不要把 self.cp.returncode 設定為 _exitcode
            ## 因為這會導致在shell內執行的command 的 exit code 被改變
            

            if self.cp.poll() is None:

                if self._exitcode == EXITCODE_DEFAULT:
                    ## The last command's exitcode not yet been retrieved.
                    ## We have to call it before closing the channel. In case like this:
                    ## with $.sudo():
                    ##       ... without calling getExitcode() ...
                    ## print($.exitcode) <== here, would raise "OSError: [Errno 9] Bad file descriptor", since file has closed
                    self.get_exit_code()
                
                ## disabled becaue this subprocess not nessary to be a shell
                #try:
                #    self.send('exit\n')
                #except OSError as e:
                #    pass
                
                try:
                    ## 2秒離開(這會卡住subprocess)
                    timeout = 2
                    self.cp.wait(timeout)
                except subprocess.TimeoutExpired as e:
                    self.log(f'timeout({timeout}s) expired when waiting for subprocess to exit')
                    self.cp.terminate()   
            else:
                self._exitcode = self.cp.poll()
            
            ## close the pty
            for fd in self._pty_to_close:
                if isinstance(fd,int):
                    os.close(fd)
                else:
                    fd.close()

            #assert self.cp.poll() is not None
            self.log8(f'self={id(self)},cp=> {self.cp} closed, exitcode={self.cp.poll()}')
            
        ## close the i/o of local buffers
        super().close()
        ## becase self.closed was set in super().close(),
        ## so that the reading thread exited after super.close() was called.
        ## that's the reason "self.cp" was set to None after super().close()
        self.cp = None
       