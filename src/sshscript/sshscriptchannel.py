import time,subprocess
import threading, os, sys
from select import select
import errno
import asyncio
try:
    from sshscripterror import SSHScriptError
except ImportError:
    from .sshscripterror import SSHScriptError
loop = asyncio.get_event_loop()
class GenericChannel(object):
    def __init__(self):
        self.allStdoutBuf = []
        self.allStderrBuf = [] 
        self.lock = threading.Lock()
        self._stdout = ''
        self._stderr = ''        
        self.dump2sys = os.environ.get('VERBOSE',sys.stdout.isatty())
        self.stdoutPrefix = os.environ.get('VERBOSE_STDOUT_PREFIX','▏').encode('utf8')
        self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','🐞').encode('utf8')
        self.stdoutDumpBuf = []
        self.stderrDumpBuf = []
        self.stdoutBuf = []
        self.stderrBuf = []
        self.lock = threading.Lock()
        # 不要0，這樣可以讓一開始就先等一等
        self._lastIOTime = time.time()

    @property
    def stdout(self):
        return self._stdout
    @property
    def stderr(self):
        return self._stderr
    
    def recv(self,secondsToWaitIOStop=1):
        # 每次執行一行命令就更新一次stdout, stderr的內容        
        self.wait(secondsToWaitIOStop) # 確保不要在還在接收資料時做結算
        self._stdout = (b''.join(self.stdoutBuf)).decode('utf8')
        self._stderr = (b''.join(self.stderrBuf)).decode('utf8')
        self.lock.acquire()
        del self.stdoutBuf[:]
        del self.stderrBuf[:]
        self.lock.release()    

        if self.dump2sys:
            if len(self.stdoutDumpBuf):
                sys.stdout.buffer.write(self.stdoutPrefix + b''.join(self.stdoutDumpBuf) + b'\n')
                sys.stdout.buffer.flush()
            if len(self.stderrDumpBuf):
                sys.stderr.buffer.write(self.stderrPrefix + b''.join(self.stderrDumpBuf) + b'\n')
                sys.stderr.buffer.flush()

        if self._stderr and self.owner.sshscript._paranoid:
            self.close()
            raise SSHScriptError(self.stderr)
 
    async def waitio(self,waitingInterval=None):
        if waitingInterval is None:
            waitingInterval = float(os.environ.get('CMD_INTERVAL',0.5))
        remain = waitingInterval - (time.time() - self._lastIOTime)
        #如果有螢幕輸出的化，幫助它順序維持正確的順序
        #sys.stdout.flush()
        #sys.stderr.flush()
        while remain > 0:
            await asyncio.sleep(remain)    
            remain = waitingInterval - (time.time() - self._lastIOTime)
        #如果有螢幕輸出的化，幫助它順序維持正確的順序
        sys.stdout.flush()
        sys.stderr.flush()

    def expect(self,s,timeout=60,stdout=True,stderr=True):
        # this is a blocking function
        # 只會搜尋目前還buffred的資料，如果要搜尋新收到的資料，
        # 須在執行命令(seld.sendline())前先呼叫 self.recv()
        data = [lambda:self._stdout, lambda:self._stderr]
        targets = []
        if stdout:
            targets.append(0)
        if stderr:
            targets.append(1)
        async def _wait():
            startIdx = 0
            startTime = time.time()
            b = s.encode('utf8')
            while True:
                if time.time() - startTime > timeout:
                    raise TimeoutError(f'Not found: {s} ' + '\n')
                for i in targets:
                    if data[i]().find(s) >= 0:
                        await self.waitio(1)
                        return
                await asyncio.sleep(0.1)
        return loop.run_until_complete(_wait())    
    
    def expectStderr(self,s,timeout=60):
        return self.expect(s,timeout,stdout=False,stderr=True)

    def expectStdout(self,s,timeout=60):
        return self.expect(s,timeout,stdout=True,stderr=False)
    
    def wait(self,seconds=None):
        async def _wait(seconds):
            await self.waitio(seconds)
        return loop.run_until_complete(_wait(seconds))                

    def __enter__(self):
        return self
    def __exit__(self,*args):
        self.wait(1)
        self.close()
    
    def sendline(self,s,secondsToWaitResponse=1):
        if not s[-1] == '\n': s += '\n'
        # 確保跟前面的一個指令有點「距離」，不要在還在接收資料時送出下一個指令
        self.wait()
        n = self.send(s)
        if secondsToWaitResponse is not None:
            self.recv(secondsToWaitResponse)
        return n

    def addStdoutData(self,x):       
        self._lastIOTime = time.time()
        if not x: return
        # 不要讓self.lock.acquire()影響self._lastIOTime
        self.lock.acquire()
        self.stdoutBuf.append(x)
        self.allStdoutBuf.append(x)
        self.lock.release()
        if self.dump2sys:
            if b'\n' in x:
                lines = ((b''.join(self.stdoutDumpBuf))+x).split(b'\n')
                for line in lines[:-1]:
                    sys.stdout.buffer.write(self.stdoutPrefix + line + b'\n')
                self.stdoutDumpBuf = [lines[-1]]
                sys.stdout.buffer.flush()
            else:
                #print('add',[x])
                self.stdoutDumpBuf.append(x)

        self._lastIOTime = time.time()
    
    def addStderrData(self,x):
        # 不要讓self.lock.acquire()影響self._lastIOTime
        self._lastIOTime = time.time()
        if not x: return
        self.lock.acquire()
        self.stderrBuf.append(x)
        self.allStderrBuf.append(x)
        self.lock.release()
        if self.dump2sys:
            if b'\n' in x:
                lines = ((b''.join(self.stderrDumpBuf))+x).split(b'\n')
                for line in lines[:-1]:
                    sys.stderr.buffer.write(self.stderrPrefix + line + b'\n')
                self.stderrDumpBuf = [lines[-1]]
                sys.stderr.buffer.flush()
            else:
                self.stderrDumpBuf.append(x)
        self._lastIOTime = time.time()

class POpenChannel(GenericChannel):
    def __init__(self,owner,cp,timeout,masterFd=None,slaveFd=None):
        super().__init__()
        self.owner = owner
        self.cp = cp
        if cp is None:
            # dummy instance for "with $<command> as ..."
            self._lastIOTime = 0
        else:
            self.masterFd = masterFd
            self.slaveFd = slaveFd
            self.timeout = timeout
            threading.Thread(target=self._reading).start()

    def send(self,s):
        self._lastIOTime = time.time()
        b = s.encode('utf-8')
        # write to popen's stdin
        os.write(self.masterFd[0],b)
        os.fsync(self.masterFd[0])
        self._lastIOTime = time.time()
    
    def _reading(self):

        buffer = {
            self.masterFd[0]: self.addStdoutData, #stdout
            self.masterFd[1]: self.addStderrData  #stderr
        }
        while buffer:           
            try:
                for fd in select(buffer, [], [])[0]:
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
                            self._lastIOTime = time.time()
                            buffer[fd](data)
                            
            except OSError as e:
                if e.errno == errno.EBADF:
                    # being closed
                    break
                else:
                    raise
        #if len(stdoutBuffer):
        #    self.addStdoutData(b''.join(stdoutBuffer))
        #if len(stderrBuffer):
        #    self.addStdoutData(b''.join(stderrBuffer))

    def close(self):
        self.wait(1) # at least 1 seconds has no io
        if self.cp: # not dummy instance
            os.close(self.masterFd[0])
            os.close(self.masterFd[1])
            os.close(self.slaveFd[0])
            os.close(self.slaveFd[1])

            while self.cp.poll() is None:
                try:
                    self.cp.wait(self.timeout)
                except subprocess.TimeoutExpired:
                    self.cp.kill()
                    break
    
        self.owner.stderr = (b''.join(self.allStderrBuf)).decode('utf8')
        self.owner.stdout = (b''.join(self.allStdoutBuf)).decode('utf8')    


class ParamikoChannel(GenericChannel):
    def __init__(self,owner,client,timeout):
        super().__init__()        
        self.owner = owner # an instance of SSHScriptDollar
        self.client = client
        if self.client:
            self.timeout = timeout
            self.channel = client.invoke_shell(term='vt100') # a paramiko.Channel
            self.stdin = self.channel.makefile_stdin('wb',-1)
            self.stdoutStream = self.channel.makefile('rb', -1)
            self.stderrStream = self.channel.makefile_stderr('r', -1) 
            self.channel.settimeout(timeout)
            threading.Thread(target=self._reading).start()

    def send(self,s):
        while not self.channel.send_ready():
            time.sleep(0.1)
        self._lastIOTime = time.time()
        n = self.channel.sendall(s)
        if n == 0:
            raise IOError('failed to write to channel')
        self._lastIOTime = time.time()
        return n
            
    def _reading(self):
    
        while not self.channel.closed:
            if self.channel.recv_ready():
                data = self.channel.recv(1024)
                self.addStdoutData(data)
            if self.channel.recv_stderr_ready():
                data = self.channel.recv_stderr(1024)
                self.addStderrData(data)
    
    def close(self):
        if self.client: # not dummy instance
            self.channel.close()
        # 此時呼叫self.recv()沒有意義，只要呼叫wait()就好
        self.wait(1)
        self.owner.stderr = (b''.join(self.allStderrBuf)).decode('utf8')
        self.owner.stdout = (b''.join(self.allStdoutBuf)).decode('utf8')    
