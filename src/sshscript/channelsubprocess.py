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

import threading, os

import time,random
import subprocess
from select import select
import errno

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
            self._dumpThread.start()

    def _start_reading(self):  
        assert self.cp is not None 
        ## important for getting correct value of command output, can not be slow
        interval = 0.1
        if self.get_pty:
            ## 2025/05/12, when get_pty is True, stdout and stdin were mixed
            def _reading():
                ## reads pty
                while self.cp.poll() is None:
                    for fd in select(self.stdouterr, [], [],interval)[0]:
                        try:
                            self._add_stdout_data(os.read(fd,1024))
                        except BlockingIOError:
                            ## when os.set_blocking(..False) this would happen
                            pass
                ## the process
                #if not self.closed:
                #    self.close()
        else:
            def _reading():
                ## reads without pty (e.g. subprocess.PIPE)
                callback = {
                    self.stdouterr[0]: self._add_stdout_data,
                    self.stdouterr[1]: self._add_stderr_data
                }
                stream = list(callback.keys())
                while self.cp.poll() is None:
                    for fd in select(stream, [], [],interval)[0]:
                        callback[fd](os.read(fd,1024))
                #if not self.closed: self.close()
        POpenChannel.count += 1
        self._reading_thread = threading.Thread(target=_reading,name=f'popen{POpenChannel.count}',daemon=True,no_patch=True)
        self._reading_thread.start()        

    def send(self,s):
        """Send data to subprocess through stdin.
        
        :s: string to send
        """
        self.log8(f'send->{[s]},{self.closed},{self.cp},self={id(self)}')
        assert not self.closed and self.cp.poll() is None, f'subprocess {self.cp} has closed,closed={self.closed}, poll={self.cp.poll()}'
        
        try:
            os.write(self.stdin,s.encode('utf-8'))
            ## would raise OSError on Ubuntu
            #os.fsync(self.stdin)
        except OSError as e:
            self.log(f'{self.cp}: OSError on writing; {e}')
            raise
        else:
            self.touchIO(False)
    
    def close(self):
        """Close channel and cleanup resources.
        
        Sends exit command, waits for subprocess to exit, and closes PTY handles.
        """
        
        if self.cp:
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
                
                ## exit the shell
                try:
                    self.send('exit\n')
                except OSError as e:
                    pass
                
                try:
                    ## 2秒離開(這會卡住subprocess)
                    timeout = 2
                    self.cp.wait(timeout)
                except subprocess.TimeoutExpired as e:
                    self.log(f'timeout({timeout}s) expired when waiting for subprocess to exit')
                    self.cp.terminate()   
            else:
                self._exitcode = self.cp.poll()
            
            ## self.close() might be call in  self._reading_thread
            if threading.current_thread() != self._reading_thread:
                while self._reading_thread.is_alive():
                    self._reading_thread.join()

            #print('close ' * 100,self._exitcode)
            ## close the pty
            for fd in self._pty_to_close:
                if isinstance(fd,int):
                    os.close(fd)
                else:
                    fd.close()

            assert self.cp.poll() is not None
            self.log8(f'self={id(self)},cp=> {self.cp} closed')
            
        ## close the i/o of local buffers
        super().close()
        ## becase self.closed was set in super().close(),
        ## so that the reading thread exited after super.close() was called.
        ## that's the reason "self.cp" was set to None after super().close()
        self.cp = None
       