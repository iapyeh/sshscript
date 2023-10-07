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
import random
#import asyncio
try:
    from .sshscripterror import  getLogger
    from .sshscriptchannelutils import Prompt, InnerConsoleSu, InnerConsoleSudo,GenericConsole,EnterConsole ,IterableEnterConsole,InnerConsoleWithDollar
except ImportError:
    from sshscripterror import  getLogger
    from sshscriptchannelutils import Prompt, InnerConsoleSu, InnerConsoleSudo,GenericConsole,EnterConsole,IterableEnterConsole,InnerConsoleWithDollar

logger = getLogger()

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

class WithChannelWrapper(GenericConsole):
    def __init__(self,channel):
        assert isinstance(channel,GenericChannel)
        self.channel = channel
        self.returnObjectWhenEnter = self
    def send(self,s):
        return self.channel.send(s)
    def input(self,s):
        return self.channel.send(s+'\n')
    def sendline(self,s,timeout=None,stderr=None,stdout=None,prompt=None):
        # prompt:bool,  enable "prompt-method" to recognize the end of a command execution
        #        if this is False and prompt is not been figuring out, use "timeout"
        # timeout:int,  wait output untill timeout seconds, default to OUTPUT_TIMEOUT and 
        #         SSH_OUTPUT_TIMEOUT ,  it is 0.5seconds (previous CMD_INTERVAL, SSH_OUTPUT_TIMEOUT).
        #         If timeout is 0, prompt is automatically False. which means waiting infinitely.
        # stdout:
        # stderr:  
        ## convert stdout and stderr arguments to the outputType argument
        if stderr is None and stdout is None:
            if timeout == 0:
                ## default to disable stdout and stderr if timeout is 0
                outputType = None
            else:
                ## default to enable stdout and stderr if timeout is 0
                outputType = 3
        elif stderr and stdout:
            outputType = 3
        elif stdout:
            outputType = 1
        elif stderr:
            outputType = 2
        else:
            outputType = 0
        return self.channel.sendline(s,outputTimeout=timeout,outputType=outputType,waitPrompt=prompt)
    ## alias for sendline
    __call__ = sendline
    exec_command = sendline

    def expect(self,rawpat,timeout=60,stdout=True,stderr=True,position=0,silent=False):
        return self.channel.expect(rawpat,timeout,stdout,stderr,position,silent)
    def expectStderr(self,rawpat,timeout=60,position=0,silent=False):
        return self.channel.expect(rawpat,timeout,False,True,position,silent)
    def expectStdout(self,rawpat,timeout=60,position=0,silent=False):
        return self.channel.expect(rawpat,timeout,True,False,position,silent)
    def wait(self,seconds=None,timeout=0):
        return self.channel.wait(seconds,timeout)
    def send_signal(self,s):
        ## wrap to popen (only work in subprocess)
        return self.channel.cp.send_signal(s)
    ## v2.0 
    def environ(self,key=None,value=None,**kw):
        ## Experimental, wrap to paramiko channel update_environment()
        ## This doesn't work in my testing.
        if isinstance(key,dict):
            kw.update(key)
        elif isinstance(key,str):
            kw[key] = value
        self.channel.channel.update_environment(kw)
    ## v2.0 disabled 
    #def lines(self,timeout=None,dataType=None):
    #    return WithChannelWrapperLines(self)(timeout,dataType)
    #def ctrlC(self):
    #    ## close the current process in channel
    #    self.channel.sendlineLock.release()
    #    self.channel.send(chr(3)+'\n')
    #def shutdown(self):
    #    ## directly close this channel(? why)
    #    if self.channel.owner.sshscript.host:
    #        self.channel.channel.shutdown(2)
    #        self.channel.channel.close()
    #    else:
    #        self.channel.cp.kill()
    # alias
    #kill = shutdown
    

    ## v2.0
    def sudo(self,password=None,expect=None,failureExpect=None,initials=None):
        return InnerConsoleSudo(self,password,expect=expect,failureExpect=failureExpect,initials=initials)
    ## v2.0
    def su(self,username,password=None,expect=None,failureExpect=None,initials=None):
        return InnerConsoleSu(self,username,password,expect=expect,failureExpect=failureExpect,initials=initials)
    ## v2.0
    def enter(self,command,expect=None,input=None,exit=None,prompt=None):
        return EnterConsole(self,command,expect,input,exit,prompt)
    ## v2.0 
    def iterate(self,command,stdout=None,stderr=None,exit=None):
        return IterableEnterConsole(self,command,stdout,stderr,exit)
    ## v2.0 
    ## experimental for fish, but not locky, it always complains
    ## No TTY for interactive shell (tcgetpgrp failed), and setpgid: Inappropriate ioctl for device
    def shell(self,command):
        return InnerConsoleWithDollar(self,command)
    ## alias, for compatibility with sshscriptsession
    onedollar = sendline
    twodollars = sendline
    ## eg: with session.withdollar() as newsession:
    ##          with newsession.withdollar() as newnewsession: <-- custome style
    ##          with newsession.shell() as newnewsession:      <-- technically should be this
    withdollar = shell

    ## v2.0
    def getPrompt(self):
        return self.channel.getPrompt()
    @property
    def waitingInterval(self):
        return self.channel.waitingInterval

    @property
    def prompt(self):
        ## self.prompt would be updated by the channel
        return self.channel.prompt
    
    
    ## propably only needed by $.enter('python')
    @prompt.setter
    def prompt(self,keywoard):
        self.channel.prompt = keywoard
        self.channel.log(DEBUG, f'** set prompt to "{self.channel.prompt}"')

    @property
    def exitcode(self):
        return self.channel.exitcode

    @property
    def stdout(self):
        return self.channel._exitcodePatternForClean.sub(r'\1',self.channel.stdout)
    @property
    def stderr(self):
        return self.channel._exitcodePatternForClean.sub(r'\1',self.channel.stderr)
    @property
    def rawstdout(self):
        return self.channel.rawstdoutForOwner()
    @property
    def rawstderr(self):
        return self.channel.rawstderrForOwner()
    
    def trim(self,text):
        return self.channel.trim(text)

    def log(self, level, msg, *args):
        return self.channel.log(level,msg, *args)
    '''
    @property
    def stdout(self):
        ## strip off the __exitcode__command and response
        if self.channel.prompt and self.channel.prompt.keyword:
            stdout = self.channel.trim(self.channel.stdout).replace(self.channel.prompt.keyword,'')
        else:
            stdout = self.channel.trim(self.channel.stdout)
        return self.channel._exitcodePatternForClean.sub(r'\1',stdout)
    @property
    def stderr(self):
        ## strip off the __exitcode__command and response
        if self.channel.prompt and self.channel.prompt.keyword:
            stderr = self.channel.trim(self.channel.stderr).replace(self.channel.prompt.keyword,'')
        else:
            stderr = self.channel.trim(self.channel.stderr)
        return self.channel._exitcodePatternForClean.sub(r'\1',stderr)
    '''
    @property
    def closed(self):
        return self.channel.closed

class GenericChannel(object):
    ## ref: https://stackoverflow.com/questions/7857352/python-regex-to-match-vt100-escape-sequences
    #self.terminalControlCodePattern = re.compile(r'(\x1b\[|\x9b)[^@-_]*[@-_]|\x1b[@-_]',re.I)
    ## fish returns more complex control codes than other shells( "\n" \x0a is excluded from the following pattern)
    terminalControlCodePattern = re.compile(r'(\x1b\[|\x9b)[^@-_]*[@-_]|\x1b[@-_]|[\x00-\x09]|[\x0b\x0f]',re.I)
    
    def __init__(self,owner):
        ## timeout of every call to "sendline" to execute commands
        self.allStdoutBuf = []
        self.allStderrBuf = [] 
        ## True when addStdoutData or addStderrData were called.
        ## False when updateStdoutStderr was called (self.stdoutBuf => self._stdout, self.stderrBuf => self._stderr)
        self._stdoutTainted = False
        self._stderrTainted = False
        self._stdout = ''
        self._stderr = ''    
        self._exitcode = -1    
        self.stdoutBuf = []
        self.stderrBuf = []
        ## Guarding self._stdout, self._stderr, self.stdoutBuf, self.stderrBuf
        self._lock = threading.Lock()
        self._lockReason = False
        ## an instance of SSHScriptDollar
        self.owner = owner
        ## assign owner's stdout and stderr
        self.owner._stdout = self.stdoutForOwner
        self.owner._stderr = self.stderrForOwner
        self.owner._rawstdout = self.rawstdoutForOwner
        self.owner._rawstderr = self.rawstderrForOwner
        self.shellToRun = self.owner.shellToRun
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
            self.stderrPrefix = b''
            self.stdoutPrefix = b''
        
        self._keepStdoutValue = True
        self._keepStderrValue = True
        self.stdoutListener = None
        self.stderrListener = None
        self.closed = False
        self.withChannelWrapper = None
        
        self._prompt = None
        self.defaultUsingPrompt = False
        ## mostly is $? for bash, sh, zsh, but it is "$status" for fish
        self._exitcodeSymbol = ('\\echo','$?')
        self._promptstacks = []
        

        self._checkExitcodeForSendline = True
        ## note: the searching text might contain terminal control characters
        ## REF: https://regex101.com/
        self._exitcodePatternOfCode = []
        self._exitcodePatternForClean = re.compile('(\W?)(?:echo )?__exitcode\d\-\-.+?\-\-\\r?\\n?',re.S)
        ## rotate the command to ask for exitcode, this is for preventing from falsely got previous exitcode
        self._exitcodeSno = 0
        self._exitcodeSnoTotal = 10
        for i in range(self._exitcodeSnoTotal):
            self._exitcodePatternOfCode.append(re.compile(f'__exitcode{i}--(\d+)--(\\r?)$',re.M|re.A))

        self._lastIOTime = time.time()
        self._lastIOType = 0

        self.exitListener = None

        self.prefixOfLog = "[channel]"

        self.sendlineLock = threading.Lock()
        self.sendlineLock.acquire()

    def pushPromptState(self,newPrompt,newDefaultUsingPrompt,shellToRun=None):
        ## save current state
        state=(self.prompt, self.defaultUsingPrompt,self._exitcodeSymbol,self.shellToRun)
        self._promptstacks.append(state)
        self.prompt = newPrompt
        self.defaultUsingPrompt = newDefaultUsingPrompt
        if shellToRun is not None: self.shellToRun = shellToRun
    def popPromptState(self):
        ## return (self._prompt, self.defaultUsingPrompt )
        self.prompt, self.defaultUsingPrompt, self._exitcodeSymbol, self.shellToRun = self._promptstacks.pop()

    @property
    def commandTimeout(self):
        raise NotImplementedError('commandTimeout not implemented')

    def getPrompt(self):
        def searchPrompt():
            ## search stderr for the prompt firstly, then search stdout 
            stuff = self.stderr
            type = 2
            if not stuff:
                type = 1
                stuff = self.stdout
                if not stuff:
                    self.log(DEBUG, f'** no stuff to find prompt **')
                    return
            self.log(DEBUG, f'searching prompt in {[stuff]}, type={[type]}.')
            p = stuff.rfind('\n')
            q = stuff.rfind('\r')
            if p == -1 and q == -1:
                keyword = self.trim(stuff.strip())
            else:
                pos = p if q == -1 else (q if p == -1 else max(p,q))
                keyword = self.trim(stuff[pos+1:].strip())
            if not keyword:
                self.log(DEBUG, f'** no keyword found for prompt **')
                return
            prompt = Prompt(self,keyword,type)
            self.log(DEBUG, f'** found prompt keyword={[keyword]}')
            return prompt
        self.wait(0.2)        
        self.updateStdoutStderr('getPrompt()')
        return searchPrompt()

    def touchIO(self,type):
        self._lastIOType = type
        self._lastIOTime = time.time()

    ## v2.0 refined routines
    def wait(self,waitingInterval,timeout=0,mustHasOutput=False):
        """
        ## Block the process at least <waitingInterval> seconds from _lastIOTime
        ## io activity = stdout or stderr got something
        ## timeout: is the maximum number of seconds of waiting
        ## when timeout==0, it means no limit if there are still i/o activity
        :mustHasOutput:
            if True, postpone counting until there are some output
            if float, same as True, but take this number as the base time to compare
               instead of taking self._lastIOTime. This would avoid too late to get the base time.
               that would lead to timeout sice there was already output before calling this function.
        """
        start = time.time()
        if mustHasOutput:
            lastT = mustHasOutput if isinstance(mustHasOutput,float) else self._lastIOTime
            endtime = (start + 10)
        else:
            endtime = (start + timeout) if (timeout > 0) else 0
        while True:
            time.sleep(0.1)
            now = time.time()
            if mustHasOutput:
                if self._lastIOTime == lastT:
                    if now < endtime: continue
                    else: raise TimeoutError(f'wait exceeded 10 seconds has no output(from:{start} to:{now}, last IO at:{lastT})')
                else:
                    ## recount endtime
                    endtime = (now + timeout) if (timeout > 0) else 0
                    ## don't enter this block again
                    mustHasOutput = False
            if waitingInterval <= now - self._lastIOTime: break
            elif endtime and now > endtime: raise TimeoutError(f'wait exceeded {timeout}')
        ##如果有螢幕輸出的話，幫助它順序維持正確的順序
        sys.stdout.flush()
        sys.stderr.flush()
    def after(self,waitingInterval):
        ## Block the execution, based on the current _lastIOTime (aka sleep)
        ## regardless of updating of the _lastIOTime
        remain = waitingInterval - (time.time() - self._lastIOTime)
        if remain > 0:
            time.sleep(remain)
        ##如果有螢幕輸出的話，幫助它順序維持正確的順序
        sys.stdout.flush()
        sys.stderr.flush()

    @property
    def stdout(self):
        self.updateStdoutStderr('.stdout')
        return self._stdout

    @property
    def stderr(self):
        self.updateStdoutStderr('.stderr')
        return self._stderr
    @property
    def exitcode(self):
        return self._exitcode

    def trim(self,text):
        ## 1 Finds all ASCII control codes and cursor positioning codes in text.
        ## 2 Remove "__exitcode__" in output
        return self._exitcodePatternForClean.sub(r'\1',self.terminalControlCodePattern.sub('',text))

    def log(self, level, msg, *args):
        logger.log(level, self.prefixOfLog + msg, *args)

    '''
    def setupSSHScriptPrompt(self,stdout=None,stderr=None,shellToRun=None):
        ## cuation: before calling this function, call "pushPromptState()"
        ## because prompt and _exitcodeSymbol would be changed
        #shellname = (shellToRun or self.owner.shellToRun).split('/')[-1]
        ## strip shell argument and take the last component of the given path
        shellname = self.shellToRun.split()[0].split('/')[-1]
        logger.debug('shellname = %s, self.shellToRun=%s, stdout=%s, stderr=%s' % (shellname,self.shellToRun,stdout,stderr))
        ## based on the ChatGPT
        self._resetBuffer()
        lastT = self._lastIOTime
        keyword = '_SSHSCRIPTPROMPT_'
        if shellname in ('ksh','bash','zsh','dash'):
            ## tested ('bash','zsh')
            self.send(f"PS1='{keyword}'\n")
        elif shellname in ('csh','tcsh',):
            self.send(f"set prompt='{keyword}'\n")
        elif shellname in ('fish',):
            self._exitcodeSymbol = ('echo','$status')
            self.send(f"function fish_prompt;echo '{keyword}';end\n")
        elif shellname in ('sh',):
            self.send(f"export PS1='{keyword}'\n")
        else:
            raise NotImplementedError(f'unknown shell "{shellname}"')
        ## before getting the prompt, let's wait a little bit
        self.wait(0.5,mustHasOutput=lastT)

        ## this doesn't work for fish, it's terminal control code is terrible!
        ## but we jsut used to know the prompt is on stdout or stderr
        #assert prompt and keyword in prompt.keyword, f'{prompt.keyword if prompt else None} does not contain {keyword}'
        #self.prompt = prompt
        type = self._lastIOType if (stdout is None and stderr is None) else (1 if stdout else 2)
        logger.debug('type = %s, self._lastIOType=%s, stdout=%s, stderr=%s' % (type,self._lastIOType,stdout,stderr))
        self.prompt(keyword,stdout=True if type==1 else False, stderr=True if type==2 else False)
        self._resetBuffer()
    '''

    def _resetBufferAll(self):
        del self.allStderrBuf[:]
        del self.allStdoutBuf[:]
        self._resetBuffer()

    def _resetBuffer(self):
        ## 清掉 console.stdout, console.stderr的數值
        ## 順便執行 verbose ，然後清掉verbose的stdout, stderr 的資料
        
        self.lock(1,'_resetBuffer()')
        del self.stdoutBuf[:]
        del self.stderrBuf[:]
        self._stdout = ''
        self._stderr = ''
        self._exitcode = -1
        self._prompt.position = 0
        newline = os.linesep.encode('utf8')
        if len(self.stdoutDumpBuf):
            if self.stdoutListener:
                ## why should we add newline at the end?
                #self.stdoutListener(1,[b''.join(self.stdoutDumpBuf) + newline])
                self.stdoutListener(1,[b''.join(self.stdoutDumpBuf)])
            if self.dump2sys:
                sys.stdout.buffer.write(self.stdoutPrefix + b''.join(self.stdoutDumpBuf) + newline)
                sys.stdout.buffer.flush()
            del self.stdoutDumpBuf[:]    
        if len(self.stderrDumpBuf):
            if self.stderrListener:
                ## why should we add newline at the end?
                #self.stderrListener(2,[b''.join(self.stderrDumpBuf) + newline])
                self.stderrListener(2,[b''.join(self.stderrDumpBuf)])
            sys.stderr.buffer.write(self.stderrPrefix + b''.join(self.stderrDumpBuf) + newline)
            sys.stderr.buffer.flush()        
            del self.stderrDumpBuf[:]
        self.lock(0)
    def lock(self, yes, reason=None):
        if yes:
            assert reason is not None, 'need reason to acquire lock'
            self._lock.acquire()
            self._lockReason = reason
        else:
            self._lock.release() 
            self._lockReason = None
    ## original name of this routine is recv(),commitIo()
    def updateStdoutStderr(self,caller=None):
        ## generate the values of console.stdout(self._stdout), console.stderr(self._stderr)
        #self.lock.acquire() ## 確保不要在還在接收資料時做結算
        try:
            self.lock(1, f'updateStdoutStderr({"" if caller is None else caller})')
            if self._stdoutTainted:
                self._stdout =  b''.join(self.stdoutBuf).decode('utf8',errors='replace')
                self._stdoutTainted = False
            if self._stderrTainted:
                self._rawstderr = b''.join(self.stderrBuf)
                self._stderr = (b''.join(self.stderrBuf)).decode('utf8',errors='replace')
                self._stderrTainted = False
        finally:
            self.lock(0)

    def stdoutForOwner(self):
        ## because we no more setup prompt, to strip out prompt is not necessary
        return self._exitcodePatternForClean.sub(r'\1', ((b''.join(self.allStdoutBuf)).decode('utf8','replace')))
    def stderrForOwner(self):
        ## because we no more setup prompt, to strip out prompt is not necessary
        return (self._exitcodePatternForClean.sub(r'\1',self.trim((b''.join(self.allStderrBuf)).decode('utf8','replace'))))
    def rawstdoutForOwner(self):
        ## because we no more setup prompt, to strip out prompt is not necessary
        return (b''.join(self.allStdoutBuf))
    def rawstderrForOwner(self):
        ## because we no more setup prompt, to strip out prompt is not necessary
        return (b''.join(self.allStderrBuf))

    def trimedStdoutForOwner(self):
        ## because we no more setup prompt, to strip out prompt is not necessary
        return self.trim((b''.join(self.allStdoutBuf)).decode('utf8','replace'))
    def trimedStderrForOwner(self):
        ## because we no more setup prompt, to strip out prompt is not necessary
        return self.trim((b''.join(self.allStderrBuf)).decode('utf8','replace'))

    ## v2.0, expectTimeout is renamed to timeout
    ## v2.0, if given rawpat is string or bytes, then it was escaped automatically
    def expect(self,rawpat,timeout=None,stdout=True,stderr=True,position=0,silent=False):
        """
        this is a blocking function
        :rawpat:bytes,str,re.Pattern or list of them
        :silent:
            if False, raise TimeoutError when timeout is reached
            if True, raise nothing, just return None when timeout is reached
        :timeout:  0: waiting forever
                   None: self.commandTimeout, aka os.environ['CMD_TIMEOUT' or 'SSH_CMD_TIMEOUT'] (default)
        """
        assert isinstance(position,int)
        
        if timeout is None: timeout = self.commandTimeout
        
        def checkStdout():
            return self._stdout + (b''.join(self.stdoutBuf)).decode('utf8','replace')
        def checkStderr():
            return self._stderr + (b''.join(self.stderrBuf)).decode('utf8','replace')            

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
                pat = re.compile(re.escape(pat.decode('utf8','replace')),re.I)
            elif isinstance(pat,str):
                pat = re.compile(re.escape(pat),re.I)
            elif isinstance(pat,re.Pattern):
                pass
            else:
                raise ValueError('expect() only accept bytes,str,re.Pattern or list of them')
            pats.append(pat)
        
        ret = None
        endTime = (time.time() + timeout) if timeout else 0
        searchedText = []
        while True:
            if endTime > 0 and time.time() > endTime:
                if silent:
                    pass
                else:
                    self.log(DEBUG,f'expect position={[position]}')
                    for text in searchedText:
                        self.log(DEBUG,f'expect searched={[text]}')
                    ret = TimeoutError(f'Not found: {rawpat}')
                break
            self.updateStdoutStderr('watching')
            del searchedText[:]
            for dataSource in targets:
                text = dataSource()
                if text == '': 
                    searchedText.append(('',''))
                    continue
                for idx,pat in enumerate(pats):
                    searchedText.append((text,text[position:]))
                    m = pat.search(text[position:])
                    if m:
                        ## 2023/8/14, since we now called updateStdoutStderr() when it was accessed by self.stdout or self.stderr
                        ## this might not be necessary anymore
                        ## 再蒐集一次，這樣最後一行才會收到_stdout裡面
                        self.updateStdoutStderr('watching end')
                        ## v2.0, re.pattern returned
                        ret = m
                        break
                if ret is not None: break
            ## 2023/8/14, since in the sendline, updateStdoutStderr() is no more been called,
            ## this block might not be necessary anymore
            ## 為了麼需要一直呼叫updateStdoutStderr()?
            ## 因為此時sendline的那個updateStdoutStderr()已經結束，需要靠expect延長時間的情況下，
            ## 協助呼叫 updateStdoutStderr()
            if ret is not None: break
            time.sleep(0.05)
        if isinstance(ret, TimeoutError):
            raise ret
        else:
            self.updateStdoutStderr('watching end')
            return ret

    def __enter__(self):
        self.withChannelWrapper =  WithChannelWrapper(self)
        return self.withChannelWrapper
    
    def __exit__(self,exc_type, exc_value, traceback):
        ## when exception was raised, this channel could be closed already
        ## so, do nothing when it happens
        if not self.closed: self.close()
    
    @property
    def prompt(self):
        return self._prompt
    
    
    ## propably only needed by $.enter('python')
    @prompt.setter
    def prompt(self,keyword):
        """
        :keyword:
            None: stop using prompt
            True,False: start/stop using prompt
            str: create a prompt and start using it
            instance of Prompt: start using it
        """
        if keyword is None:
            self.defaultUsingPrompt = False
        elif isinstance(keyword, bool):
            if keyword and self._prompt is None:
                raise f'prompt is not set, can not enable it'
            self.defaultUsingPrompt = keyword
        elif isinstance(keyword, str) or isinstance(keyword, re.Pattern):
            self.defaultUsingPrompt = True
            self._prompt.keyword = keyword
        elif isinstance(keyword, Prompt):
            self.defaultUsingPrompt = True
            self._prompt = keyword
        else:
            raise ValueError(f'invalid value for prompt:{keyword}')
    

    def waitCommandToComplete(self,outputTimeout,waitPrompt=None):
        ## block until this command has finished,
        ## but user cand still input by the returned stdin
        ## Lets hold up at this porint to receive data(eg. ls)
        ## In case of data comes in repeatly (ex tcpdump),
        ## A good practice is that user have to set outputTimeout=0 (not waiting)
        ## , then handle output data within loop. Otherwise "self.wait" would be blocked.
        if waitPrompt is None and self.defaultUsingPrompt:
            self._prompt.expect(outputTimeout)
        elif waitPrompt is None:
            ## assert not self.defaultUsingPrompt
            self.wait(outputTimeout)
        elif waitPrompt:
            ## if self._prompt is not working, it would failover to self.wait(outputTimeout)
            self._prompt.expect(outputTimeout)
        else:
            self.wait(outputTimeout)       

    def getExitcode(self,timeout=None):
        ## 
        self.send(f'{self._exitcodeSymbol[0]} __exitcode{self._exitcodeSno}--{self._exitcodeSymbol[1]}--\n')
        m = self.expect(self._exitcodePatternOfCode[self._exitcodeSno],timeout=timeout,silent=True)
        if m is None:
            self._exitcode = -1
        else:
            self._exitcode = int(m.group(1))
        self._exitcodeSno = (self._exitcodeSno + 1) % self._exitcodeSnoTotal
    def sendline(self,line,outputTimeout=None,outputType=None,waitPrompt=None):
        ## line: commands to run, accept multiple lines from v1.1.13
        ## waitPrompt: if False, not expect(self.prompt) after command was sent.
        ##             this is for 'interactive-command' such as 'python'
        ##             if None, using self.daultUsingPrompt
        ## outputTimeout: timeout of waiting io to stop,
        ##             if None, ussing self.waitingInterval
        ## if lookup prompt enabled(waitPrompt/self.daultUsingPrompt) and outputTimeout are given,
        ##    the outputTimeout is useless, the timeout of prompt.expect() is self.commandTimeout
        ##    BUT if the prompt is not working (no keyword)
        ##    it will failover to self.wait(outputTimeout)
        ## if outputTimeout == 0, user hints this is command won't end
        ##    such as "tcpdump", default type would be 0, 
        ##    -- which means _keepStdoutValue and _keepStderrValue would be auto False,unless user enable them explicitly
        ##    waitPrompt would be set to False

        ## ensure that there is no more output, especially at the beginning when a new shell is started
        self.sendlineLock.acquire()

        ## every sendline() would reset stdoutListener,stderrListener(set by looping lines())
        self.stdoutListener = None
        self.stderrListener = None
        ## every sendline() would reset _keepStdoutValue, _keepStderrValue(set by pervious sendline())
        self._keepStdoutValue = True
        self._keepStderrValue = True

        ## v2.0 keep empty lines
        if isinstance(line,str):
            lines = [x.lstrip() for x in line.strip().splitlines()]
        elif isinstance(line,list) or isinstance(line,tuple): ## bug-fixed in v1.1.18
            lines = [x.strip() for x in line]
        else:
            lines = []

        if len(lines) == 0:
            ## block the process at least self.waitingInterval
            self.after(self.waitingInterval)
            self.sendlineLock.release()
            return
    
        if outputTimeout is None: 
            ## if CMD_INTERVAL is too short, then it is too early to call updateStdoutStderr()
            ## the result would be missing the command's outputs
            outputTimeout = self.waitingInterval 
        elif outputTimeout == 0:
            waitPrompt = False
            ## auto turn off _keepStdoutValue and _keepStderrValue if this is 
            ## a ever-run command. unless user set them explicitly
            if outputType is None:
                self._keepStdoutValue = False
                self._keepStderrValue = False

        ## default is to output both stdout and stderr
        if outputType is not None:
            self._keepStdoutValue = outputType & 1 == 1
            self._keepStderrValue = outputType & 2 == 2

        ## cleanup and reset buffers of both console.stdout and console.stderr
        ## Should not depends on updateStdoutStderr(), because soon after 1st line was send, data would be received.
        ## But updateStdoutStderr() was called after the last line (so, it does not cleanup buffers)
        self._resetBuffer()

        ## for powershell 好像是這邊送\n,收會收\n,這邊送\r\n，收會收\r\n,
        newline = '\n'
        for idx,line in enumerate(lines):
            '''
            disabled, seems not necessary
            ## Before sending a new command, wait a while to keep "distance" from the previous command
            ## Because we might still in receiving outputs of it.
            ## Note: process like tcpdump would continuously outputing.
            ##       it would block the self.wait()，so we have to give the call a timeout (30)
            ##       But a good practice should put tcpdump only in an individual call to sendline()
            if idx > 0 : self.wait(self.waitingInterval,30)
            '''
            self.send(line+newline)
            if idx < len(lines) - 1:
                ## not the last one
                self.waitCommandToComplete(outputTimeout,waitPrompt)
                    
        ## Here, all lines were sent
        if outputTimeout == 0:
            ## user hint that this is a long run command
            ## it makes this becomes a non-blocking call
            pass
        else:
            ## No need to call updateStdoutStderr()
            ## Just call updateStdoutStderr() When user wants to get console.stdout or console.stderr
            ## (See WithChannelWrapper().stdout or WithChannelWrapper().stderr)       
            self.waitCommandToComplete(outputTimeout,waitPrompt)
            ## $.enter(python3) doesn't need to get exitcode, but $, $.su and $.sudo do
            if self._checkExitcodeForSendline:
                self.getExitcode()
                error = self.owner.checkExitcode(self.exitcode,self.stderr)
                if error:
                    self.sendlineLock.release()
                    ## just "raise error" , and do nothing else, this would gain perfectly what we want for the example:
                    ##    $.careful(1)
                    ##    with $#!/bin/bash as console:
                    ##        try:
                    ##            $ls -l /non/existing
                    ##        except SSHScriptError as e:
                    ##            assert e.code == 1
                    ##            assert console.exitcode == 1 <-- key, we want this to be 1, not 0 (the shell's exitcode)
                    ##    assert console.exitcode == 0 ## console.exitcode is the shell's exitcode
                    ##    assert $.exitcode == 0
                    raise error
            self.sendlineLock.release()
            return self.stdout, self.stderr, self.exitcode

    def addStdoutData(self,newbytes):  
        ## x: bytes
        #print(f'<<<o:{time.time()}',newbytes)
        if not newbytes:return
        self.touchIO(1)
        lines = None
        bNewline = b'\n'
        self.lock(1,f'addStdoutData({self._keepStdoutValue})')

        ## self._keepStdoutValue would be false when there is a inifite loop
        ## which is requesting its stdout's value  by "for line in console.stdout(0)"
        if self._keepStdoutValue:
            self.stdoutBuf.append(newbytes)
            self.allStdoutBuf.append(newbytes)
        
        ## split stdoutDumpBuf's data into lines
        ## and extract them out of the stdoutDumpBuf
        try:
            p = newbytes.rindex(bNewline)
        except ValueError:
            self.stdoutDumpBuf.append(newbytes)
        else:
            lines = (b''.join(self.stdoutDumpBuf)+newbytes[:p]).split(bNewline)
            del self.stdoutDumpBuf[:]
            if p < len(newbytes) - 1:
                self.stdoutDumpBuf.append(newbytes[p+1:])
        self._stdoutTainted = True
        self.lock(0)

        if lines:
            if self.stdoutListener:
                self.stdoutListener(1,[x+bNewline for x in lines])
            if self.dump2sys:
                sys.stdout.buffer.write(bNewline.join([self.stdoutPrefix + x  for x in lines])+bNewline)
                sys.stdout.buffer.flush()

    def addStderrData(self,newbytes):
        #print(f'<<<e:{time.time()}',newbytes)
        if not newbytes: return
        self.touchIO(2)
        lines = None
        bNewline = b'\n'
        self.lock(1,f'addStderrData({self._keepStderrValue})')
        ## self._keepStderrValue would be false when there is a inifite loop
        ## which is requesting its stdout's value  by "for line in console.stdout(0)"
        if self._keepStderrValue:
            self.stderrBuf.append(newbytes)
            self.allStderrBuf.append(newbytes)

        ## fix bug v1.1.18        
        ## split stderrDumpBuf's data into lines
        ## and extract them out of the stderrDumpBuf
        try:
            p = newbytes.rindex(bNewline)
        except ValueError:
            self.stderrDumpBuf.append(newbytes)
        else:
            lines = (b''.join(self.stderrDumpBuf)+newbytes[:p]).split(bNewline)
            del self.stderrDumpBuf[:]
            if p < len(newbytes) - 1:
                ## leave residual bytes in the stderrDumpBuf
                self.stderrDumpBuf.append(newbytes[p+1:])
        
        self._stderrTainted = True
        self.lock(0)
        if lines is not None:
            if self.stderrListener:
                self.stderrListener(2,[x+bNewline for x in lines])
            if self.dump2sys:
                sys.stderr.buffer.write(bNewline.join([self.stderrPrefix + x  for x in lines])+bNewline)
                sys.stderr.buffer.flush()
    def close(self):
        ## dump the last content in stdoutDumpBuf and stderrDumpBuf
        ## No need to call self.updateStdoutStderr()
        ## this will stop threads of reading
        self.closed = True

        bNewline = b'\n'
        if len(self.stdoutDumpBuf):
            lines = (b''.join(self.stdoutDumpBuf)).split(bNewline)
            if self.stdoutListener:
                self.stdoutListener(1,[x+bNewline for x in lines])
            if self.dump2sys:
                sys.stdout.buffer.write(bNewline.join([self.stdoutPrefix + x  for x in lines])+bNewline)
                sys.stdout.buffer.flush()
        if len(self.stderrDumpBuf):
            lines = (b''.join(self.stderrDumpBuf)).split(bNewline)
            if self.stderrListener:
                self.stderrListener(1,[x+bNewline for x in lines])
            if self.dump2sys:
                sys.stderr.buffer.write(bNewline.join([self.stderrPrefix + x  for x in lines])+bNewline)
                sys.stderr.buffer.flush()

class POpenChannel(GenericChannel):
    def __init__(self,owner,cp,masterFd,stdin,ptyForClose):
        super().__init__(owner)
        self.prefixOfLog = "[POpenChannel]"
        self._prompt = Prompt(self,None,type=2)
        self.cp = cp
        self.stdin = stdin
        self.ptyForClose = ptyForClose
        if cp is None:
            ## dummy instance for "with $<command> as ..."
            pass
        else:
            self.masterFd = masterFd
            if sys.platform == 'win32':
                def _win32ReadingStderr():
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

                def _win32ReadingStdout():
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
                threading.Thread(target=_win32ReadingStdout).start()
                threading.Thread(target=_win32ReadingStderr).start()
            else:
                ## read pty
                def _reading():
                    buffer = {
                        self.masterFd[0]: self.addStdoutData,  #stdout
                        self.masterFd[1]: self.addStderrData  #stderr
                    }
                    #if len(self.masterFd) == 2:
                    #    buffer[self.masterFd[1]]= self.addStderrData
                    #while (not self.closed) and buffer:
                    while (self.cp.poll() is None):
                        try:
                            ## timeout = 1
                            for fd in select(buffer, [], [],1)[0]:
                                try:
                                    if isinstance(fd,int):
                                        data = os.read(fd, 1024) # read available
                                    else:
                                        data = fd.read1()
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
                            time.sleep(0.01)
                        except OSError as e:
                            if e.errno == errno.EBADF:
                                # being closed
                                break
                            else:
                                raise 

                threading.Thread(target=_reading,name='sshscriptchannel-popen-read').start()
                ## this is not necessary
                #self.setupSSHScriptPrompt(stderr=True)
        self.sendlineLock.release()

    @property
    def waitingInterval(self):
        ## wait for io activity to stop
        return self.owner.waitingInterval
    @property
    def commandTimeout(self):
        return self.owner.commandTimeout
    
    def send(self,s):
        ## disable, sensitive data might be shown
        #self.log(DEBUG,f'{threading.current_thread().native_id} send:{[s]}')
        os.write(self.stdin,s.encode('utf-8'))
        ## this would crashed in linux for pty 
        #os.fsync(self.stdin)
    
    def close(self):
        super().close()
        self.log(DEBUG,f'closing popen channel {self.cp}')
        ## force "sendline" not to expect(self.prompt)
        self.prompt = None
        error = None
        if self.cp: # not dummy instance
            ## in both case of with-dollar and two-dollars
            ## send "exit" to ensure that the retcode is 0 (otherwise it will be 1)
            ## because in the sshscriptdollars.py both of them invoking a subprocess with "prompt".
            #if self.owner.inWith: self.send('exit\n')
            try:
                self.send('exit\n')
            except OSError:
                ## in case, the subprocess has already closed due to error
                ## eg with $ as console:
                ##        console('ls -l /non/existing/folder')
                pass
            timeout = self.commandTimeout 
            try:
                self._exitcode = self.cp.wait(timeout)
            except subprocess.TimeoutExpired as e:
                self.log(DEBUG,f'timeout({timeout}s) expired when waiting for subprocess to exit')
                error = e
                self.cp.terminate()   
                self._exitcode = self.cp.returncode             
            ## copy one to owner
            self.owner.exitcode = self._exitcode 
            ## help to close the pty
            try:
                os.close(self.ptyForClose[0])
                os.close(self.ptyForClose[1])
            except:
                ## in case, the subprocess has already closed due to error
                ## eg with $ as console:
                ##        console('ls -l /non/existing/folder')
                pass
        '''
        if self.cp and self.owner.exitcode != 0:
            if sys.platform == 'win32':
                error = WinError()       # OSError
                lasterror = GetLastError() # int
                self.log(DEBUG,f'[subprocess][win]last error = {[lasterror]}')
                self.log(DEBUG,f'[subprocess][win]error= {[error.errno]}')
                self.owner.exitcode = lasterror
            else:
                self.log(DEBUG,f'[subprocess] error={error}')
        '''
        #self.log(DEBUG,f'[subprocess] exitcode={self.owner.exitcode}')

        
class ParamikoChannel(GenericChannel):
    def __init__(self,owner,client):
        super().__init__(owner)
        self.prefixOfLog = "[ParamikoChannel]"
        self._prompt = Prompt(self,None,type=1)
        def _reading():
            ## this is run in thread
            while not (self.channel.closed or self.channel.exit_status_ready()):
                while self.channel.recv_stderr_ready():
                    self.addStderrData(self.channel.recv_stderr(4096))
                while self.channel.recv_ready():
                    self.addStdoutData(self.channel.recv(4096))     
        ## experimental
        if isinstance(client,paramiko.client.SSHClient):
            ## paramiko's invoke_shell
            self.client = client
            ## a paramiko.Channel
            self.channel = client._transport.open_session()
            threading.Thread(target=_reading,name='sshscriptchannel-ssh-read1').start()
            if self.owner.inWith:
                ## should enable pty, because without it, interactive python, mysql client won't work.
                ## but it also produce "prompt" into stdout. that is a problem.
                self.channel.get_pty()
            else:
                ## twodollars, no pty support
                pass
            self.channel.set_combine_stderr(False)
            self.channel.settimeout(self.commandTimeout)
            baseLastIOTime = self._lastIOTime            
            if self.owner.usershell:
                self.channel.exec_command(self.owner.usershell)
            else:
                ## default to bash
                self.owner.usershell = 'bash'
                self.shellToRun = self.owner.shellToRun = 'bash'
                self.channel.exec_command('bash')
            if self.owner.inWith:
                ## wait for message of today, prompt of the shell
                self.wait(0.25,mustHasOutput=baseLastIOTime)
            else:
                ## twodollars, no pty support, no output, don't wait
                pass                
            '''
        elif 0 and isinstance(client,paramiko.client.SSHClient):
                ## paramiko's invoke_shell
                self.client = client
                ## a paramiko.Channel
                self.channel = client._transport.open_session()
                ## should enable pty, because without it, interactive python, mysql client won't work.
                ## but it also produce "prompt" into stdout. that is a problem.
                self.channel.get_pty()
                self.channel.set_combine_stderr(False)
                self.channel.invoke_shell()            
                self.channel.settimeout(self.commandTimeout)
                threading.Thread(target=_reading,name='sshscriptchannel-ssh-read1').start()
        elif isinstance(client,paramiko.channel.Channel):
            ## custom shell
            self.client = None
            self.channel = client
            self.stdin = self.channel.makefile_stdin('wb',-1)
            self.stdoutStream = self.channel.makefile('rb', -1)
            self.stderrStream = self.channel.makefile_stderr('r', -1) 
            self.channel.settimeout(self.commandTimeout)
            threading.Thread(target=_reading,name='sshscriptchannel-ssh-read2').start()
            self.wait(0.5,mustHasOutput=True)
            #prompt = self.getPrompt()
            #if prompt is not None: self._prompt = prompt
            #print('promit=',prompt)
            '''
        else:
            ## dummy
            self.client = None
            self.channel = None

        ## check exitcode from now on
        if self.client:        
            if self.owner.inWith:
                if not self.shellToRun.split('/')[-1] in ('dash',):
                    ## help to remove garbage from stdout or stderr
                    ## this is helpful for  ssh 's shell 
                    #lastT = self._lastIOTime
                    self.send('stty -echo\n')
                    ## don't use mustHasOutput, because when PS1="", this would be blocked
                    #self.wait(0.25,mustHasOutput=lastT)
                    self.wait(0.25)
                ## don't need when using exec_command method to execute shell
                #self.setupSSHScriptPrompt(stdout=True)
                pass
        self._resetBufferAll()
        self.sendlineLock.release()
    @property
    def waitingInterval(self):
        return self.owner.waitingIntervalSSH
    @property
    def commandTimeout(self):
        return self.owner.commandTimeoutSSH

    def send(self,s):
        self.log(DEBUG,f'{threading.current_thread().native_id},{self.owner.sshscript.host} send:{[s]}')
        while not self.channel.send_ready(): time.sleep(0.01)
        self.channel.sendall(s)

    def close(self):
        super().close()

        ## force "sendline" not to expect(self.prompt)
        self.prompt = None

        if self.channel is None:
            pass
        else:
            self.log(DEBUG,f'[{self.owner.sshscript.host}] closing ssh channel')

            ## automatically send exit to shell
            try:
                ## this is important to ensure the last command to complete (not knowing why)
                self.after(1)

                ## note:
                ##     before self.channel.closed() is called, self.channel.exit_status_ready() eems always false
                ## v2.0, user setup custom shell
                if self.owner.usershell:  self.send('exit\n')
                
                ## (to do: should we call exit to exit paramiko's invoke_shell?)
                ## call self.send, not self.sendline, because self.sendline will reset .stdout and .stderr
                if not self.channel.exit_status_ready():
                    self.send('exit\n')                
                    self.channel.shutdown_write()
                timeout = time.time() + 10
                while time.time() < timeout:
                    if self.channel.exit_status_ready():
                        break
                    time.sleep(0.01)
                if self.channel.exit_status_ready():
                    self.owner.exitcode = self.channel.recv_exit_status()
                    self.log(DEBUG,f'[{self.owner.sshscript.host}] smoothly closed, exitcode= {self.owner.exitcode}')
                else:
                    #self.channel.close()
                    if self.channel.exit_status_ready():
                        self.owner.exitcode = self.channel.recv_exit_status()                        
                    self.log(DEBUG,f'[{self.owner.sshscript.host}] unsmoothly closed, exitcode= {self.owner.exitcode}')
                self.channel.close()                    
            except paramiko.ssh_exception.SSHException as e:
                self.log(DEBUG,f'[{self.owner.sshscript.host}] error on closing:{e}')
            except OSError as e:
                self.log(DEBUG,f'[{self.owner.sshscript.host}] error on closing:{e}')

