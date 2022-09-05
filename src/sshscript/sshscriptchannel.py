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
from queue import Empty, SimpleQueue
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

#https://stackoverflow.com/questions/34504970/non-blocking-read-on-os-pipe-on-windows
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

class WithChannelWrapper(object):
    def __init__(self,channel):
        self.c = channel
    def sendline(self,s=os.linesep,finalWaitingInterval=None):
        return self.c.sendline(s,finalWaitingInterval)
    def expect(self,rawpat,timeout=60,stdout=True,stderr=True):
        return self.c.expect(rawpat,timeout,stdout,stderr)
    def expectStderr(self,rawpat,timeout=60):
        return self.c.expect(rawpat,timeout,False,True)
    def expectStdout(self,rawpat,timeout=60):
        return self.c.expect(rawpat,timeout,True,False)
    def wait(self,seconds=None):
        return self.c.wait(seconds)

    @property
    def channel(self):
        return self.c.channel
    @property
    def stdout(self):
        return self.c.stdout
    @property
    def stderr(self):
        return self.c.stderr
    


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
        # an instance of SSHScriptDollar
        self.owner = owner
        self.defaultWaitingInterval = self.owner.waitingIntervalSSH if self.owner.sshscript.host else self.owner.waitingInterval
        
        if os.environ.get('VERBOSE'):
            # verbose-related
            self.stdoutDumpBuf = []
            self.stderrDumpBuf = []
            self.dump2sys = True
            if sys.platform  == 'win32':
                self.stdoutPrefix = os.environ.get('VERBOSE_STDOUT_PREFIX','| ').encode('utf8')
                self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','- ').encode('utf8')
            else:
                self.stdoutPrefix = os.environ.get('VERBOSE_STDOUT_PREFIX','🟩').encode('utf8')
                self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','🟨').encode('utf8')
        else:
            self.dump2sys = False

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    def _log(self, level, msg, *args):
        self.logger.log(level, "[sshscriptC]" + msg, *args)

    # original is recv()
    def commitIo(self,resetBuffer=True):
        # 確保不要在還在接收資料時做結算
        # 先wait之後再acquire lock,不要太早acquire
        self.lock.acquire()
        # 每次執行一行命令就更新一次stdout, stderr的內容    
        self._stdout = (b''.join(self.stdoutBuf)).decode('utf8',errors='ignore')
        self._stderr = (b''.join(self.stderrBuf)).decode('utf8',errors='ignore')
        if resetBuffer:
            del self.stdoutBuf[:]
            del self.stderrBuf[:]
        if self.dump2sys:
            newline = os.linesep.encode('utf8')
            if len(self.stdoutDumpBuf):
                sys.stdout.buffer.write(self.stdoutPrefix + b''.join(self.stdoutDumpBuf) + newline)
                sys.stdout.buffer.flush()
            if len(self.stderrDumpBuf):
                sys.stderr.buffer.write(self.stderrPrefix + b''.join(self.stderrDumpBuf) + newline)
                sys.stderr.buffer.flush()
            del self.stdoutDumpBuf[:]
            del self.stderrDumpBuf[:]
        self.lock.release()  
    async def waitio(self,waitingInterval):
        await self.owner.sshscript.waitio(waitingInterval)
        #如果有螢幕輸出的話，幫助它順序維持正確的順序
        sys.stdout.flush()
        sys.stderr.flush()

    def expect(self,rawpat,timeout=60,stdout=True,stderr=True):
        # rawpat:bytes,str,re.Pattern or list of them

        # this is a blocking function
        def checkStdout():
            return self._stdout + (b''.join(self.stdoutBuf)).decode('utf8','ignore')
        def checkStderr():
            return self._stderr + (b''.join(self.stderrBuf)).decode('utf8','ignore')            

        #data = [checkStdout, checkStderr]
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
                            return rawpat[idx]
                if self.owner.sshscript._lastIOTime != lastIo:
                    lastIo = self.owner.sshscript._lastIOTime
                    self.commitIo(False)
                await asyncio.sleep(0.1)
        return self.loop.run_until_complete(_wait())    
        
       
    def wait(self,seconds):
        async def _wait(seconds):
            await self.waitio(seconds)
        return self.loop.run_until_complete(_wait(seconds))                

    def __enter__(self):
        return WithChannelWrapper(self)
    
    def __exit__(self,*args):
        if self.owner.cp:
            # 要等程式確實跑完
            timeout = float(os.environ.get('CMD_TIMEOUT',60))
            try:
                self.owner.cp.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.owner.cp.kill()
                self.owner.cp.communicate()             
            self.owner.cp = None

        self.owner.sshscript.touchIO()
        self.wait(self.defaultWaitingInterval)
        self.close()
    
    def sendline(self,line='',finalWaitingInterval=None):
        # accept multiple lines from v1.1.13
        newline = '\n'

        if finalWaitingInterval is None: 
            # if CMD_INTERVAL is too short, too early to call commitIO()
            # the results is missing the command's outputs
            # so, plus 0.2 be min waiting interval
            finalWaitingInterval = max(self.defaultWaitingInterval , 0.2)
        
        if isinstance(line,str):
            lines = [x.lstrip() for x in line.splitlines() if x.lstrip()]
        elif isinstance(line,list) or isinstance(tuple):
            lines = [x.lstrip() for x in line if x.lstrip()]
        else:
            lines = []
        
        if len(lines) == 0:
            # 這種空白列，不要呼叫self.commitIo，也就是不要reset $.stdout, $.stderr
            #subprocess.stdin does not like "newline"
            #self.send(newline)
            self.owner.sshscript.touchIO()
            self.wait(self.defaultWaitingInterval)
            return

        # for powershell, 好像是這邊送\n,收會收\n,這邊送\r\n，收會收\r\n
        # 使用者可以放 # 列，當作緩衝
        for line in lines:
            #if not line: line = newline
            if not line.endswith(newline): line += newline
            self._log(DEBUG,f'[sshscriptchannel]sendline({self.defaultWaitingInterval}):{line[:-1]}')
            self.send(line)
            # 確保跟前面的一個指令有點「距離」，不要在還在接收資料時送出下一個指令
            # 在sshscriptdollar中呼叫前已經先wait過，因此很多行時，先送再wait
            # self.send has touchIO(), so no need to touchIO here, just wait()
            self.wait(self.defaultWaitingInterval)
        
        #self.owner.sshscript.touchIO()
        self.wait(finalWaitingInterval)
        self.commitIo()

    def addStdoutData(self,x):  
        # 不要讓self.lock.acquire()影響self._lastIOTime
        if not x:return
        self.owner.sshscript.touchIO()
        lines = None
        bNewline = b'\n'
        self.lock.acquire()
        self.stdoutBuf.append(x)
        self.allStdoutBuf.append(x)
        if self.dump2sys:
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
            for line in lines:
                sys.stdout.buffer.write(self.stdoutPrefix + line + bNewline)
            sys.stdout.buffer.flush()
    
    def addStderrData(self,x):
        # 不要讓self.lock.acquire()影響self._lastIOTime
        if not x: return
        self.owner.sshscript.touchIO()
        lines = None
        bNewline = b'\n'
        self.lock.acquire()
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
            for line in lines:
                sys.stderr.buffer.write(self.stderrPrefix + line + bNewline)
            sys.stderr.buffer.flush()

class POpenChannel(GenericChannel):
    def __init__(self,owner,cp,timeout,masterFd=None,slaveFd=None):
        super().__init__(owner)
        self.loop = self.owner.sshscript.loop
        self.closed = False
        self.cp = cp
        if cp is None:
            # dummy instance for "with $<command> as ..."
            #self._lastIOTime = 0
            pass
        else:
            self.masterFd = masterFd
            self.slaveFd = slaveFd
            self.timeout = timeout
            if sys.platform == 'win32':
                threading.Thread(target=self._readingStdout).start()
                threading.Thread(target=self._readingStderr).start()
            else:
                threading.Thread(target=self._reading).start()
            self.queue = SimpleQueue()
    '''  
            threading.Thread(target=self._sending).start()
    def send(self,s):
        self.queue.put(s)
    def _sending(self):
        while not self.closed:
            try:
                s = self.queue.get_nowait()
            except Empty:
                pass
            else:
                try:
                    self.cp.stdin.write(s.encode('utf-8'))
                    self.cp.stdin.flush()
                except:
                    pass
                else:
                    self.owner.sshscript.touchIO()
    '''
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
                    #print(2,os.fstat(self.masterFd[1]))
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
                    #print('stdout erro',e,e.errno,WinError())
                    pass
                    #print(1,os.fstat(self.masterFd[1]))
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
                        #print('<<',data)
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
        self.closed = True
        error = None
        if self.cp: # not dummy instance
            os.close(self.masterFd[0])
            os.close(self.masterFd[1])
            os.close(self.slaveFd[0])
            os.close(self.slaveFd[1])
            self.cp.stdin.close()
            try:
                self.owner.exitcode = self.cp.wait(self.timeout)
            except subprocess.TimeoutExpired as e:
                error = e
                self.cp.kill()
            

        self.owner.sshscript.touchIO()
        self.wait(self.defaultWaitingInterval)

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
        
        if self.owner.exitcode > 0 and self.owner.sshscript._careful:
            raise SSHScriptCareful(error,code=self.owner.exitcode)

class ParamikoChannel(GenericChannel):
    def __init__(self,owner,client,timeout):
        super().__init__(owner)
        self.loop = self.owner.sshscript.loop
        if isinstance(client,paramiko.client.SSHClient):
            self.client = client
            self.timeout = timeout
            self.channel = client.invoke_shell(term='vt100') # a paramiko.Channel
            self.stdin = self.channel.makefile_stdin('wb',-1)
            self.stdoutStream = self.channel.makefile('rb', -1)
            self.stderrStream = self.channel.makefile_stderr('r', -1) 
            self.channel.settimeout(timeout)
            threading.Thread(target=self._reading).start()
            #self.queue = SimpleQueue()
            #threading.Thread(target=self._sending).start()
        elif isinstance(client,paramiko.channel.Channel):
            self.client = None
            self.channel = client
            self.timeout = timeout
            self.stdin = self.channel.makefile_stdin('wb',-1)
            self.stdoutStream = self.channel.makefile('rb', -1)
            self.stderrStream = self.channel.makefile_stderr('r', -1) 
            self.channel.settimeout(timeout)
            threading.Thread(target=self._reading).start()
            #self.queue = SimpleQueue()
            #threading.Thread(target=self._sending).start()
        else:
            # dummy
            self.client = None
            self.channel = None
    '''
    def send(self,s):
        self.queue.put(s)
    def _sending(self):
        while not (self.channel.closed or self.channel.exit_status_ready()):
            try:
                s = self.queue.get_nowait()
            except Empty:
                pass
            else:
                while not self.channel.send_ready(): time.sleep(0.01)                
                self.channel.sendall(s)
                self.owner.sshscript.touchIO()
    '''
    def send(self,s):
        while not self.channel.send_ready(): time.sleep(0.01)
        self.channel.sendall(s)
        self.owner.sshscript.touchIO()

    def _reading(self):
        # this is run in thread
        while not (self.channel.closed or self.channel.exit_status_ready()):
            while self.channel.recv_stderr_ready():
                self.addStderrData(self.channel.recv_stderr(1024))
            while self.channel.recv_ready():
                self.addStdoutData(self.channel.recv(1024))
        while not (self.channel.exit_status_ready()):
            time.sleep(0.01)
        self.owner.exitcode = self.channel.recv_exit_status()
        self._log(DEBUG,f'[ssh] exit code= {self.owner.exitcode}')
        if self.owner.exitcode > 0 and self.owner.sshscript._careful:
            raise SSHScriptCareful(self.owner.exitcode,code=self.owner.exitcode)

    def close(self):
        # 此時呼叫self.commitIo()沒有意義，只要呼叫wait()就好
        self.owner.sshscript.touchIO()
        self.wait(self.defaultWaitingInterval)
        if self.channel: # not dummy instance
            self.channel.shutdown_write()
            self.channel.close()

        self.lock.acquire()
        self.owner.stderr = (b''.join(self.allStderrBuf)).decode('utf8',errors='ignore')
        self.owner.stdout = (b''.join(self.allStdoutBuf)).decode('utf8',errors='ignore')    
        self.lock.release()
