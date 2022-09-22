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
from gc import DEBUG_SAVEALL
#from queue import Empty, SimpleQueue
import threading, os, sys, re
import paramiko
from logging import DEBUG
import time
import subprocess
from select import select
import errno
import asyncio
try:
    from .sshscripterror import SSHScriptCareful, getLogger
except ImportError:
    from sshscripterror import SSHScriptCareful, getLogger

##https://stackoverflow.com/questions/34504970/non-blocking-read-on-os-pipe-on-windows
if sys.platform == 'win32':
    import msvcrt
    from ctypes import windll, byref, wintypes, GetLastError, WinError, POINTER
    from ctypes.wintypes import HANDLE, DWORD, BOOL
    from ctypes import POINTER

    LPDWORD = POINTER(DWORD)

    PIPE_NOWAIT = wintypes.DWORD(0x00000001)

    ERROR_NO_DATA = 232

    def pipe_no_wait(pipefd):
        """ pipefd is a integer as returned by os.pipe """

        SetNamedPipeHandleState = windll.kernel32.SetNamedPipeHandleState
        SetNamedPipeHandleState.argtypes = [HANDLE, LPDWORD, LPDWORD, LPDWORD]
        SetNamedPipeHandleState.restype = BOOL

        h = msvcrt.get_osfhandle(pipefd)

        res = windll.kernel32.SetNamedPipeHandleState(h, byref(PIPE_NOWAIT), None, None)
        if res == 0:
            print(WinError())
            return False
        return True    

class WithChannelWrapperLines(object):
    def __init__(self,wcw):
        self.wcw = wcw
        ## set by user when looping (for line in console.lines(timeout=1))
        self.timeout = None
        self.type = 1
    def __call__(self,timeout=None,dataType=None):
        ## default timeout is CMD_TIMEOUT or 60 seconds
        ## dfault dataType is stdout
        ## dataType = 1 for stdout, 2 for stderr, 3 for stdout,stderr, others is stdout
        if isinstance(timeout,float) or isinstance(timeout,int):
            self.timeout = timeout
        if isinstance(dataType,int):
            self.type = dataType
        self.wcw.c._log(DEBUG,f'looping timeout={self.timeout},type={self.type}')
        return self
    def __next__(self):
        pass
    def __iter__(self):
        ## self.c.stdoutBuf is initial value
        queue = []
        lock = self.wcw.c.lock
        def add2queue(type,lines):
            try:
                lock.acquire()
                if self.type == 3:
                    queue.append((type,lines))
                else:
                    queue.append(lines)
            finally:
                lock.release()
        if self.type == 2:
            self.wcw.c.stderrListener = add2queue
            queue.append(self.wcw.c.stderrBuf)
        elif self.type == 3:
            self.wcw.c.stdoutListener = add2queue
            self.wcw.c.stderrListener = add2queue
            queue.append((1,self.wcw.c.stdoutBuf))
            queue.append((2,self.wcw.c.stderrBuf))
        else: ## 1 and others
            self.wcw.c.stdoutListener = add2queue
            queue.append(self.wcw.c.stdoutBuf)

        timeout = float(os.environ.get('CMD_TIMEOUT',60)) if self.timeout is None else self.timeout
        endtime = time.time() + timeout if timeout else 0

        ## consuming queue starts
        def iterTuple(item):
            for line in item[1]:
                yield (item[0],line.decode('utf8','ignore'))
        def iterList(item):
            for line in item:
                yield line.decode('utf8','ignore')
        iterator = iterTuple if self.type == 3 else iterList
        while not self.wcw.c.closed:
            n = len(queue)
            if n == 0:
                if timeout and (time.time() >= endtime):
                    #if self.timeout is None:
                    #    ## user has not set timeout, let's make a noice
                    #    raise TimeoutError(f'No data in {timeout} seconds')
                    #else:
                    #    ## timeout was set by user, break silently
                    #    break
                    raise TimeoutError(f'No data in {timeout} seconds')
                else:
                    time.sleep(0.1)
                    continue
            try:
                lock.acquire()
                for i in range(n):
                    ## convert to str for loop's value
                    g = iterator(queue[i])
                    while True:
                        try:
                            yield next(g)
                        except StopIteration:
                            break
                del queue[0:n]
                lock.release()
                ## reschedule timeout
                if timeout: endtime = time.time() + timeout
            finally:
                try:
                    lock.release()
                except RuntimeError:
                    pass
        ## codes here would never be called

class WithChannelWrapper(object):
    def __init__(self,channel):
        self.c = channel
        self.haveToCommitIo = None
    def sendline(self,s=os.linesep,timeout=None,dataType=None):
        self.haveToCommitIo = True
        return self.c.sendline(s,timeout,dataType)
    def expect(self,rawpat,timeout=60,stdout=True,stderr=True):
        return self.c.expect(rawpat,timeout,stdout,stderr)
    def expectStderr(self,rawpat,timeout=60):
        return self.c.expect(rawpat,timeout,False,True)
    def expectStdout(self,rawpat,timeout=60):
        return self.c.expect(rawpat,timeout,True,False)
    def wait(self,seconds=None):
        return self.c.wait(seconds)
    def lines(self,timeout=None,dataType=None):
        return WithChannelWrapperLines(self)(timeout,dataType)
    def send_signal(self,s):
        ## wrap to popen (only work in subprocess)
        return self.c.cp.send_signal(s)
    def shutdown(self):
        if self.c.owner.sshscript.host:
            self.c.channel.shutdown(2)
            self.c.channel.close()
        else:
            self.c.cp.kill()
    # alias
    kill = shutdown
    
    @property
    def channel(self):
        return self.c.channel
    @property
    def stdout(self):
        if self.haveToCommitIo:
            self.c.updateStdoutStderr()
            self.haveToCommitIo = False
        return self.c._stdout
    @property
    def stderr(self):
        if self.haveToCommitIo:
            self.c.updateStdoutStderr()
            self.haveToCommitIo = False
        return self.c._stderr
    @property
    def closed(self):
        return self.c.closed

class GenericChannel(object):
    
    def __init__(self,owner):
        self.logger = getLogger()
        self.allStdoutBuf = []
        self.allStderrBuf = [] 
        self._stdout = ''
        self._stderr = ''        
        self.stdoutBuf = []
        self.stderrBuf = []
        self.lock = threading.Lock()
        ## an instance of SSHScriptDollar
        self.owner = owner
        self.defaultWaitingInterval = self.owner.waitingIntervalSSH if self.owner.sshscript.host else self.owner.waitingInterval
        
        self.stdoutDumpBuf = []
        self.stderrDumpBuf = []
        if os.environ.get('VERBOSE'):
            ## verbose-related
            self.dump2sys = True
            if sys.platform  == 'win32':
                self.stdoutPrefix = os.environ.get('VERBOSE_STDOUT_PREFIX','| ').encode('utf8')
                self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','- ').encode('utf8')
            else:
                self.stdoutPrefix = os.environ.get('VERBOSE_STDOUT_PREFIX','🟩').encode('utf8')
                self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','🟨').encode('utf8')
        else:
            self.dump2sys = False

        
        self._keepStdoutValue = True
        self._keepStderrValue = True
        self.stdoutListener = None
        self.stderrListener = None
        self.closed = False
    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    def _log(self, level, msg, *args):
        self.logger.log(level, "[sshscriptC]" + msg, *args)

    def _resetBuffer(self):
        ## 清掉 console.stdout, console.stderr的數值
        ## 順便執行 verbose ，然後清掉verbose的stdout, stderr 的資料
        
        del self.stdoutBuf[:]
        del self.stderrBuf[:]

        newline = os.linesep.encode('utf8')
        if len(self.stdoutDumpBuf):
            if self.stdoutListener: self.stdoutListener(1,[b''.join(self.stdoutDumpBuf) + newline])
            if self.dump2sys:
                sys.stdout.buffer.write(self.stdoutPrefix + b''.join(self.stdoutDumpBuf) + newline)
                sys.stdout.buffer.flush()
            del self.stdoutDumpBuf[:]    
        if len(self.stderrDumpBuf):
            if self.stderrListener: self.stderrListener(2,[b''.join(self.stderrDumpBuf) + newline])
            sys.stderr.buffer.write(self.stderrPrefix + b''.join(self.stderrDumpBuf) + newline)
            sys.stderr.buffer.flush()        
            del self.stderrDumpBuf[:]
            
    ## original is recv(),commitIo()
    def updateStdoutStderr(self):
        ## 產生console.stdout, console.stderr的資料
        ## 確保不要在還在接收資料時做結算
        self.lock.acquire()
        ## 每次執行一行命令就更新一次stdout, stderr的內容    
        self._stdout = (b''.join(self.stdoutBuf)).decode('utf8',errors='ignore')
        self._stderr = (b''.join(self.stderrBuf)).decode('utf8',errors='ignore')
        self.lock.release()  
    
    async def waitio(self,waitingInterval,timeout):
        await self.owner.sshscript.waitio(waitingInterval,timeout)
        #如果有螢幕輸出的話，幫助它順序維持正確的順序
        sys.stdout.flush()
        sys.stderr.flush()

    async def afterio(self,waitingInterval):
        await self.owner.sshscript.afterio(waitingInterval)
        #如果有螢幕輸出的話，幫助它順序維持正確的順序
        sys.stdout.flush()
        sys.stderr.flush()

    def wait(self,seconds,timeout=0):
        async def _wait(seconds,timeout):
            await self.waitio(seconds,timeout)  
        return self.loop.run_until_complete(_wait(seconds,timeout)) 

    def after(self,seconds):
        async def _after(seconds):
            await self.afterio(seconds)  
        return self.loop.run_until_complete(_after(seconds))

    def expect(self,rawpat,timeout=60,stdout=True,stderr=True):
        ## rawpat:bytes,str,re.Pattern or list of them

        ## this is a blocking function
        def checkStdout():
            return self._stdout + (b''.join(self.stdoutBuf)).decode('utf8','ignore')
        def checkStderr():
            return self._stderr + (b''.join(self.stderrBuf)).decode('utf8','ignore')            

        targets = []
        if stdout:
            targets.append(checkStdout)
        if stderr:
            targets.append(checkStderr)
        
        pats = []
        if not (isinstance(rawpat,list) or isinstance(rawpat,tuple)):
            rawpat = [rawpat]
        for pat in rawpat:
            if isinstance(pat,bytes):
                pat = re.compile(pat.decode('utf8'),re.I)
            elif isinstance(pat,str):
                pat = re.compile(pat,re.I)
            elif isinstance(pat,re.Pattern):
                pass
            else:
                raise ValueError('expect() only accept bytes,str,re.Pattern or list of them')
            pats.append(pat)
        async def _wait():
            startTime = time.time()
            lastIo = self.owner.sshscript._lastIOTime
            while True:
                if time.time() - startTime > timeout:
                    raise TimeoutError(f'Not found: {pat} ' + os.linesep)
                for dataSource in targets:
                    di = dataSource()
                    for idx,pat in enumerate(pats):
                        if pat.search(di):
                            self._log(DEBUG,f'expect matched {pat}')
                            ## 再蒐集一次，這樣最後一行才會收到_stdout裡面
                            self.updateStdoutStderr()
                            return rawpat[idx]
                ## 為了麼需要一直呼叫updateStdoutStderr()?
                ## 因為此時sendline的那個updateStdoutStderr()已經結束，需要靠expect延長時間的情況下，
                ## 協助呼叫 updateStdoutStderr()
                if self.owner.sshscript._lastIOTime != lastIo:
                    lastIo = self.owner.sshscript._lastIOTime
                    self.updateStdoutStderr()
                await asyncio.sleep(0.1)
        return self.loop.run_until_complete(_wait())    

    def __enter__(self):
        return WithChannelWrapper(self)
    
    def __exit__(self,*args):

        ## 把stdoutBuffer中殘餘的資料補到_stderr上
        ## 都已經要離開了，好像沒必要
        #self.updateStdoutStderr(False)

        ## 多等這小段時間對$.stdout,$.stderr是有意義
        ## 但這應該是使用者自己要利用sendline的timeout解決的問題
        ## 在這裡多等一小段，作這件事可能是錯的
        #self.owner.sshscript.touchIO()
        #self.wait(self.defaultWaitingInterval,3)
        
        self.close()
    
    def sendline(self,line,outputTimeout=None,outputType=None):
        ## accept multiple lines from v1.1.13
        ## if outputTimeout == 0, user hints this is command won't end
        ## such as "tcpdump", default type would be 0, 
        ## which means _keepStdoutValue and _keepStderrValue would be auto False
        ## unless user enable them explicitly

        ## every sendline() would reset stdoutListener,stderrListener(set by looping lines())
        self.stdoutListener = None
        self.stderrListener = None
        ## every sendline() would reset _keepStdoutValue, _keepStderrValue(set by pervious sendline())
        self._keepStdoutValue = True
        self._keepStderrValue = True

        if isinstance(line,str):
            lines = [x.lstrip() for x in line.splitlines() if x.lstrip()]
        elif isinstance(line,list) or isinstance(tuple):
            lines = [x.lstrip() for x in line if x.lstrip()]
        else:
            lines = []

        if outputTimeout is None: 
            ## if CMD_INTERVAL is too short, too early to call updateStdoutStderr()
            ## the results is missing the command's outputs
            ## so, plus 0.2 be min waiting interval
            #finalWaitingInterval = max(self.defaultWaitingInterval , 0.2)
            outputTimeout = self.defaultWaitingInterval 
        elif outputTimeout == 0:
            ## auto turn off _keepStdoutValue and _keepStderrValue if this is 
            ## a ever-run command. unless user set them explicitly
            if outputType is None:
                self._keepStdoutValue = False
                self._keepStderrValue = False

        if outputType is not None:
            self._keepStdoutValue = outputType & 1 == 1
            self._keepStderrValue = outputType & 2 == 2

        ## 執行前先清一次buffer及reset console.stdout, console.stderr
        ## 不能等updateStdoutStderr()，因為只要送出第一行就會有資料進來。
        ## 而updateStdoutStderr()是最後一列送完才執行。(所以它不清buffer)
        self.lock.acquire()
        self._stdout = ''
        self._stderr = ''
        self._resetBuffer()
        self.lock.release()

        if len(lines) == 0:
            ## subprocess.stdin does not like "newline"
            #self.send(newline)
            self.owner.sshscript.touchIO()
            self.after(self.defaultWaitingInterval)
            return

        ## for powershell, 好像是這邊送\n,收會收\n,這邊送\r\n，收會收\r\n
        ## 使用者可以放 # 列，當作緩衝
        newline = '\n'
        for idx,line in enumerate(lines):
            if not line.endswith(newline): line += newline
            self._log(DEBUG,f'[{self.owner.sshscript.host}]sendline({self.defaultWaitingInterval}):{[line[:-1]]}')
            self.send(line)
            ## 確保跟前面的一個指令有點「距離」，不要在還在接收資料時送出下一個指令
            ## 在sshscriptdollar中呼叫前已經先wait過，因此很多行時，先送再wait
            ## self.send has touchIO(), so no need to touchIO here, just wait()
            ## 另一方面，像是tcpdump一直輸出，會導致self.wait卡住，因此給wait一個timout
            if idx < len(lines) - 1: self.wait(self.defaultWaitingInterval,30)
            ## 最後一個指令不用等（讓sendline下一行可以開始執行，不會被sendline卡住,ex.loop）
            ## 如果使用者刻意要等，可以用expect
        
        if outputTimeout == 0:
            ## user hint that this is a long run command
            pass
        else:
            self.owner.sshscript.touchIO()
            ## 這裡需要hold住，收取那些馬上就有反應的程式的資料(ex. ls)
            ## 但是如果資料一直不停進來(ex tcpdump),對於這一種情況
            ## 如果使用者自己不設定finalWaitingInterval==0，這裡會變成卡住
            self.wait(outputTimeout)
            
            ## 此處不updateStdoutStderr()
            ## 1. 等使用者要拿取stdout or stderr時才updateStdoutStderr()
            ## 2. 離開此with-command時(__exit__) 會呼叫 self.updateStdoutStderr()

    def addStdoutData(self,x):  
        ## x is a byte
        ## 不要讓self.lock.acquire()影響self._lastIOTime
        if not x:return
        
        self.owner.sshscript.touchIO()
        lines = None
        bNewline = b'\n'
        self.lock.acquire()

        ## self._keepStdoutValue would be false when there is a inifite loop
        ## which is requesting its stdout's value  by "for line in console.stdout(0)"
        if self._keepStdoutValue:
            self.stdoutBuf.append(x)
            self.allStdoutBuf.append(x)

        try:
            p = x.rindex(bNewline)
        except ValueError:
            self.stdoutDumpBuf.append(x)
        else:
            lines = (b''.join(self.stdoutDumpBuf)+x[:p]).split(bNewline)
            del self.stdoutDumpBuf[:]
            if p < len(x) - 1:
                self.stdoutDumpBuf.append(x[p+1:])

        self.lock.release()

        if lines:
            if self.stdoutListener:
                self.stdoutListener(1,[x+bNewline for x in lines])
            if self.dump2sys:
                sys.stdout.buffer.write(bNewline.join([self.stdoutPrefix + x  for x in lines])+bNewline)
                sys.stdout.buffer.flush()

    def addStderrData(self,x):
        ## 不要讓self.lock.acquire()影響self._lastIOTime
        if not x: return
        self.owner.sshscript.touchIO()
        lines = None
        bNewline = b'\n'
        self.lock.acquire()
        ## self._keepStderrValue would be false when there is a inifite loop
        ## which is requesting its stdout's value  by "for line in console.stdout(0)"
        if self._keepStderrValue:
            self.stderrBuf.append(x)
            self.allStderrBuf.append(x)

        if self.dump2sys:
            try:
                p = x.rindex(bNewline)
            except ValueError:
                self.stderrDumpBuf.append(x)
            else:
                lines = (b''.join(self.stderrDumpBuf)+x[:p]).split(bNewline)
                del self.stderrDumpBuf[:]
                if p < len(x) - 1:
                    self.stderrDumpBuf.append(x[p+1:])
        
        self.lock.release()
        if lines:
            if self.stderrListener:
                self.stderrListener(2,[x+bNewline for x in lines])
            sys.stderr.buffer.write(bNewline.join([self.stderrPrefix + x  for x in lines])+bNewline)
            sys.stderr.buffer.flush()

class POpenChannel(GenericChannel):
    def __init__(self,owner,cp,masterFd=None,slaveFd=None):
        super().__init__(owner)
        self.loop = self.owner.sshscript.loop
        self.closed = False
        self.cp = cp
        if cp is None:
            ## dummy instance for "with $<command> as ..."
            pass
        else:
            self.masterFd = masterFd
            self.slaveFd = slaveFd
            if sys.platform == 'win32':
                threading.Thread(target=self._readingStdout).start()
                threading.Thread(target=self._readingStderr).start()
            else:
                threading.Thread(target=self._reading).start()

    def send(self,s):
        self.cp.stdin.write(s.encode('utf-8'))
        self.cp.stdin.flush()
        self.owner.sshscript.touchIO()
      
    def _readingStderr(self):
        assert pipe_no_wait(self.masterFd[1])
        while (not self.closed):
            try:
                data = os.read(self.masterFd[1],1024)
                self.addStderrData(data)
            except OSError as e:
                if e.errno == 22:
                    pass
                elif GetLastError() != ERROR_NO_DATA:
                    print (dir(e), e.errno, GetLastError())
                    print(WinError())
                    raise

    def _readingStdout(self):
        assert pipe_no_wait(self.masterFd[0])
        while (not self.closed):
            try:
                data = os.read(self.masterFd[0],1024)
                self.addStdoutData(data)
            except OSError as e:
                if e.errno == 22:
                    pass
                elif GetLastError() != ERROR_NO_DATA:
                    print (dir(e), e.errno, GetLastError())
                    print(WinError())
                    raise

    def _reading(self):
        buffer = {
            self.masterFd[0]: self.addStdoutData, #stdout
            self.masterFd[1]: self.addStderrData  #stderr
        }
        while (not self.closed) and buffer:
            try:
                for fd in select(buffer, [], [],1)[0]:
                    try:
                        data = os.read(fd, 1024) # read available
                    except OSError as e:
                        if e.errno == errno.EIO:
                            pass
                        elif e.errno == errno.EBADF:
                            pass
                        else:
                            raise #XXX cleanup
                        del buffer[fd] # EIO means EOF on some systems
                    else:
                        if not data: # EOF
                            del buffer[fd]
                        else:
                            buffer[fd](data)
            except OSError as e:
                if e.errno == errno.EBADF:
                    # being closed
                    break
                else:
                    raise

    def close(self):
        self._log(DEBUG,'closing popen channel')
        error = None
        if self.cp: # not dummy instance
            ## 要等程式確實跑完
            timeout = float(os.environ.get('CMD_TIMEOUT',60))
            try:
                self.cp.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._log(DEBUG,f'timeout({timeout}s) expired when communicating with popen')
                self.cp.kill()
                self.cp.communicate()             

            try:
                self.owner.exitcode = self.cp.wait(timeout)
            except subprocess.TimeoutExpired as e:
                error = e
                self.cp.kill()
            os.close(self.masterFd[0])
            os.close(self.masterFd[1])
            os.close(self.slaveFd[0])
            os.close(self.slaveFd[1])
            self.cp.stdin.close()
            self._log(DEBUG,f'exitcode={self.owner.exitcode}')
        self.owner.sshscript.touchIO()
        self.wait(self.defaultWaitingInterval,3)

        ## this will stop threads of reading
        self.closed = True

        self.lock.acquire()
        self.owner.stderr = (b''.join(self.allStderrBuf)).decode('utf8',errors='ignore')
        self.owner.stdout = (b''.join(self.allStdoutBuf)).decode('utf8',errors='ignore')    
        self.lock.release()

        if self.cp and self.owner.exitcode != 0:
            if sys.platform == 'win32':
                error = WinError()       # OSError
                lasterror = GetLastError() # int
                self._log(DEBUG,f'[subprocess][win]last error = {[lasterror]}')
                self._log(DEBUG,f'[subprocess][win]error= {[error.errno]}')
                self.owner.exitcode = lasterror
            else:
                self._log(DEBUG,f'[subprocess] error={error}')
        
        self._log(DEBUG,f'[subprocess] exitcode={self.owner.exitcode}')
        
        if self.owner.exitcode is not None and self.owner.exitcode > 0 and self.owner.sshscript._careful:
            raise SSHScriptCareful(error,code=self.owner.exitcode)

class ParamikoChannel(GenericChannel):
    def __init__(self,owner,client):
        super().__init__(owner)
        self.loop = self.owner.sshscript.loop
        timeout = float(os.environ.get('CMD_TIMEOUT',60))
        if isinstance(client,paramiko.client.SSHClient):
            self.client = client
            self.channel = client.invoke_shell(term='vt100') # a paramiko.Channel
            self.stdin = self.channel.makefile_stdin('wb',-1)
            self.stdoutStream = self.channel.makefile('rb', -1)
            self.stderrStream = self.channel.makefile_stderr('r', -1) 
            self.channel.settimeout(timeout)
            threading.Thread(target=self._reading).start()
        elif isinstance(client,paramiko.channel.Channel):
            self.client = None
            self.channel = client
            self.stdin = self.channel.makefile_stdin('wb',-1)
            self.stdoutStream = self.channel.makefile('rb', -1)
            self.stderrStream = self.channel.makefile_stderr('r', -1) 
            self.channel.settimeout(timeout)
            threading.Thread(target=self._reading).start()
        else:
            ## dummy
            self.client = None
            self.channel = None

    def send(self,s):
        while not self.channel.send_ready(): time.sleep(0.01)
        self.channel.sendall(s)
        self.owner.sshscript.touchIO()

    def _reading(self):
        ## this is run in thread
        while not (self.channel.closed or self.channel.exit_status_ready()):
            while self.channel.recv_stderr_ready():
                self.addStderrData(self.channel.recv_stderr(1024))
            while self.channel.recv_ready():
                self.addStdoutData(self.channel.recv(1024))
    def close(self):
        self.closed = True
        ## 此時呼叫self.updateStdoutStderr()沒有意義，只要呼叫wait()就好
        self.owner.sshscript.touchIO()
        if self.channel is None:
            pass
        else:
            self._log(DEBUG,f'[{self.owner.sshscript.host}]closing ssh channel')
            if not self.channel.exit_status_ready():
                self.sendline('exit')
            timeout = time.time() + float(os.environ.get('CMD_TIMEOUT',60))
            while not (self.channel.exit_status_ready()):
                time.sleep(0.01)
                if time.time() >= timeout:
                    #raise RuntimeError('ssh timeout')
                    self._log(DEBUG,f'[ssh] wait for exit status timeout({os.environ.get("CMD_TIMEOUT",60)}s)')
                    self.channel.shutdown_write()
                    self.channel.close()
                    break
            if self.channel.exit_status_ready():
                self.owner.exitcode = self.channel.recv_exit_status()
            else:
                pass
            self._log(DEBUG,f'[ssh] exit code= {self.owner.exitcode}')
        self.lock.acquire()
        self.owner.stderr = (b''.join(self.allStderrBuf)).decode('utf8',errors='ignore')
        self.owner.stdout = (b''.join(self.allStdoutBuf)).decode('utf8',errors='ignore')    
        self.lock.release()
        if self.owner.exitcode is not None and self.owner.exitcode > 0 and self.owner.sshscript._careful:
            raise SSHScriptCareful(self.owner.exitcode,code=self.owner.exitcode)
