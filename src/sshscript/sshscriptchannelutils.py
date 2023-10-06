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
import re
import time
try:
    from .sshscripterror import  getLogger
except ImportError:
    from sshscripterror import  getLogger

logger = getLogger()

class Prompt(object):
    def __init__(self,channel,keyword,type=1):
        self._keyword = None
        ## bash output prompt at stderr, so lets' default is to check stderr
        self._type = 2
        self.channel = channel
        self.type = type
        self.keyword = keyword
        self.position = 0
    def clone(self):
        return Prompt(self.channel, self.keyword,self._type)
    def expect(self,outputTimeout):
        """
        :outputTimeout:
            the "no-output" interval from last output(stdout or stderr)
        """
        timeout = self.channel.commandTimeout
        timeout = 3
        if self.pattern is None:
            ## failover to channel's default wait() method
            logger.debug(f'****** ****** ******1 prompt {self} failover to wait()')
            self.channel.wait(outputTimeout)
        elif self._type == 1:
            try:
                m = self.channel.expect(self.pattern,timeout=timeout,stdout=True,stderr=False,position=self.position)
            except TimeoutError:
                logger.debug(f'****** ****** ****** prompt {self} not matched')
                logger.debug(f'stdout={self.channel.stdout}')
                raise
            else:
                self.position += m.end() + 1
                logger.debug(f'****** ****** ******2 prompt {self} matched')
                ## ensure all data has been received
                self.channel.wait(0.1)
        elif self._type == 2:
            try:
                m = self.channel.expect(self.pattern,timeout=timeout,stdout=False,stderr=True,position=self.position)
            except TimeoutError:
                logger.debug(f'****** ****** ****** prompt {self} not matched')
                logger.debug(f'stderr={self.channel.stderr}')
                raise
            else:
                self.position += m.end() + 1
                logger.debug(f'****** ****** ******3 prompt {self} matched')
                ## ensure all data has been received
                self.channel.wait(0.1)
        else:
            raise ValueError(f'Invalid prompt type:{self._type}')
    def __repr__(self):
        return f'<Prompt {"stdout" if self._type==1 else "stderr"}:"{self._keyword}",position={self.position}>'
    def __call__(self,keyword,stdout=False,stderr=False):
        assert isinstance(stdout,bool) and isinstance(stderr,bool)
        self.keyword = keyword
        if stdout: self.type = 1
        elif stderr: self.type = 2
        logger.debug(f'** __call__ set prompt to "{self}" ({stdout},{stderr})')
    @property
    def keyword(self):
        return self._keyword
    @keyword.setter
    def keyword(self, value):
        assert value is None or isinstance(value,str) or isinstance(value,bool) or isinstance(value,re.Pattern), f'{value} is unaccepted'
        if not value:
            ## valus in ('', None, False)
            self._keyword = None
            self.pattern = None
        elif isinstance(value,str):
            self._keyword = value
            self.pattern = re.compile(re.escape(value))
        else:
            assert isinstance(value,re.Pattern)
            self._keyword = value.pattern
            self.pattern = value
    @property
    def type(self):
        return self._type
    @type.setter
    def type(self, value):
        self._type = value


class GenericConsole(object):
    def __init__(self):
        ## self.returnObjectWhenEnter should be assigned by subclasses
        self.returnObjectWhenEnter = None

class InnerConsole(GenericConsole):
    def __init__(self,wcw,username,password=None,expect=None,failureExpect=None,initials=None):
        """
        :initials: when successful loging
            - a shell command to execute when the new shell has opened
            - a list of shell commands to execute when the new shell has opened
            - a callable func(new_console) to be called when the new shell has opened
        """
        ## WithChannelWrapper is inherited from GenericConsole
        ## no more assert isinstance(wcw,WithChannelWrapper), since WithChannelWrapper
        ## is not accessible in this file
        assert isinstance(wcw,GenericConsole) 
        self.wcw = wcw
        self.username = username
        ## instance of SSHScriptChannel
        self.channel = wcw.channel
        self.password = password
        ## depends on encodig, this could be "密碼”,  not "password"
        self._expect = expect or 'password'
        self.failureExpect = failureExpect or expect or ['password','sorry']
        self.initials = initials
        self.shellToRun = self.channel.shellToRun
        self.returnObjectWhenEnter = self.wcw
        self.exitListener = None
    def callInitials(self):
        if isinstance(self.initials,str):
            self.channel.send(self.initials+'\n')
        elif isinstance(self.initials,list) or isinstance(self.initials,tuple):
            for command in self.initials:
                self.channel.send(command+'\n')
        elif callable(self.initials):
            self.initials(self.channel)
    def __enter__(self):
        ## wait a moment to let  self.channel._resetBuffer() really work
        ## that we can get a clear buffer
        def succeded():
            ## because user's prompt might be chaning depends on pwd
            ## so we need to set up a chnonically unchanged prompt
            ## don't use the prompt got from initial message
            #prompt = self.channel.getPrompt()
            #if prompt is not None:
            #    self.channel.prompt = prompt

            '''
            Todo: maybe we should try to figure out which shell we are running
                  for sudo and su console
                stdout, stderr = self.sendline('\echo $0')
            '''

            ## 'stty -echo' for dash is absolutely nothing, unlike bash or others
            shellname = self.shellToRun.split('/')[-1]
            if shellname not in ('dash',):
                ## help to remove garbage from stdout or stderr
                #baseLastIOTime = self.channel._lastIOTime
                self.channel.send('stty -echo\n')
                ## don't use mustHasOutput, because when PS1="", this would be blocked
                #self.channel.wait(0.25,mustHasOutput=baseLastIOTime) # wait for stty -echo to finish
                self.channel.wait(0.25)
            
            self.callInitials()
            ## this is not necessary
            #self.channel.setupSSHScriptPrompt(shellToRun=self.shellToRun)

        self.channel.sendlineLock.acquire()
        ## by prompt.clone(), we can keep both prompts are of the same type (stdout or stderr))
        ## 2023/9/27 "prompt" might not required anymore, since we don not set prompt anymore.
        prompt = self.channel.prompt.clone()
        prompt.keyword = ''
        self.channel.pushPromptState(prompt,False,shellToRun=self.shellToRun)
        self.channel._resetBuffer()
        self.wcw.send(self.command+'\n')
        if self.password:
            m = self.wcw.expect(self._expect,timeout=2,silent=True)
            if m is None:
                ## we don't get prompt for password, take this is successful.
                ## when we sudo twice, this would be the case. sudo doesnot ask for password at the second time.
                succeded()
            else:
                logger.debug('sending password')
                ## have to call resetBuffer, otherwise the already recieved "password" prompt
                ## will confuse up when checking if "password" was asked again
                self.channel._resetBuffer()
                self.wcw.send(self.password+'\n')
                ## check failure
                if self.failureExpect:
                    ## asking again?
                    m = self.wcw.expect(self.failureExpect,timeout=2,silent=True)
                    if m is None:
                        succeded()
                    else:
                        raise RuntimeError(f'unable to sudo by "{self.command}" due to "{m.group(0)}" was prompted')
                else:
                    succeded()
        else:
            ## test if we got a prompt asking for password
            m = self.wcw.expect(self._expect,timeout=2,silent=True)
            if m is None:
                succeded()
            else:
                raise RuntimeError(f'unable to sudo with password due to "{m.group(0)}" was prompted')
        self.channel.sendlineLock.release()
        return self.returnObjectWhenEnter
    def __exit__(self,exc_type, exc_value, traceback):
        ## before exiting, we need to restore the prompt state,
        ## it makes the send() of "exit" would expect the correct prompt
        ## and we need to call _resetBuffer() for sending exitto clear the stdout and stderr buffers.
        ## for the next command to get correct stdout and stderr data in buffers.
        self.channel.sendlineLock.acquire()
        self.channel.popPromptState()
        self.channel.send('exit\n')
        self.channel.waitCommandToComplete(self.channel.waitingInterval,False)
        self.channel.getExitcode(timeout=3)        
        ## this is necessary for next command to work properly
        ## (maybe it is because that the "exit" a shell takes time)
        self.channel.wait(1)
        ## don't need to cleanup, let user can get value of .stdout and .stderr from outer console
        #self.channel._resetBuffer()
        self.channel.sendlineLock.release()
        ## for wrapper (see sshscriptsession.sudo)
        if self.exitListener: self.exitListener(exc_type, exc_value, traceback)

    ## might be called by AppConsole()
    ## wrap to top-level console (self.wcw)
    def expect(self,rawpat,timeout=60,stdout=True,stderr=True,position=0,silent=False):
        return self.wcw.expect(rawpat,timeout,stdout,stderr,position,silent)
    def getPrompt(self):
        return self.wcw.getPrompt()
    def sendline(self,*args,**kwargs):
        return self.wcw.sendline(*args,**kwargs)
    def wait(self,*args,**kwargs):
        return self.wcw.wait(*args,**kwargs)
    def send(self,*args,**kwargs):
        return self.wcw.send(*args,**kwargs)
    def open(self,*args,**kwargs):
        return self.wcw.open(*args,**kwargs)

class InnerConsoleSu(InnerConsole):
    def __init__(self,wcw,username,password=None,expect=None,failureExpect=None,initials=None):
        ## sometimes, "sudo" does not require a password, so password is optional
        super().__init__(wcw,username,password,expect=expect,failureExpect=failureExpect,initials=initials)
        self.command = f'\su {self.username}'
class InnerConsoleSudo(InnerConsole):
    def __init__(self,wcw,password=None,expect=None,failureExpect=None,initials=None):
        ## sometimes, "sudo" does not require a password, so password is optional
        super().__init__(wcw,'root',password,expect=expect,failureExpect=failureExpect,initials=initials)
        ## not really knows why, for subprocess we need '-S' 
        ## \sudo == no alias
        self.command = '\sudo --stdin su'
## for "fish" we need wrapper it in a bash shell
##     with $#!bash as console:
##         with console.shell('fish') as subconsole:
##             ... run in fish ...
class InnerConsoleWithDollar(InnerConsole):
    def __init__(self,wcw,command):
        ## command: the shell command
        super().__init__(wcw,'',None,expect=None,failureExpect=None,initials=None)
        assert isinstance(command,str)
        command = command.strip()
        if command.startswith('#!'): command = command[2:].strip()
        if command == '':
            ## case like "with $ as console" inside another shell   
            ## with $.suudo() as shell
            ##     with $ as subsshell
            command = 'bash'
        self.command = command
        self.shellToRun = command



class EnterConsole(object):
    def __init__(self,parentConsole,command,expect=None,input=None,exit=None,prompt=None):
        """
        ## parentConsole in ( WithChannelWrapper , InnerConsoleSu, InnerConsoleSudo )
        :prompt:
            if not given(None), this function would try to figure out the prompt
        """
        assert isinstance(parentConsole,GenericConsole) 
        self.parentConsole = parentConsole
        ## self.channel is sshscript's channel
        self.channel = self.parentConsole.channel
        self.command = command
        self.expect = expect
        self.input = input
        self.prompt = prompt
        ## default exit comand to ^D
        self.exit = exit or chr(4)
        self.returnObjectWhenEnter = self.parentConsole.returnObjectWhenEnter
    def __enter__(self):
        ## wait a moment to let  self.channel._resetBuffer() really work
        ## that we can get a clear buffer
        self.channel.sendlineLock.acquire()

        self.channel._resetBuffer()
        baseLastIOTime = self.channel._lastIOTime
        self.parentConsole.send(self.command+'\n')
        if self.expect:
            ## eg. mysql client
            try:
                ## somthing like "Enter password" of mysql
                ## or just something to wait if there is no self.input was given
                self.parentConsole.expect(self.expect,timeout=5)
            except TimeoutError:
                raise RuntimeError(f'{self.command} failure, {self.expect} does not show up')
            else:
                if self.input:
                    self.channel._resetBuffer()
                    baseLastIOTime = self.channel._lastIOTime
                    self.parentConsole.send(self.input+'\n')
                    self.channel.wait(0.5,mustHasOutput=baseLastIOTime)
                    #self.channel.waitCommandToComplete(self.channel.waitingInterval,False)
                    m = self.parentConsole.expect(self.expect,timeout=1,silent=True)
                    if m is None:
                        ## suppose ok
                        pass
                    else:
                        ## suppose failed to login
                        raise RuntimeError(f'{self.command} failure due to "{m.group(0)}"')
        else:
            ## if nothing to expect(eg. python),  at least wait for output stopped
            ## this helps to get correct prompt, it is important for getting correct stdout for every line of input.
            self.channel.wait(1,mustHasOutput=baseLastIOTime)
        
        if self.prompt is None:
            prompt = self.parentConsole.getPrompt()
            if prompt is None:
                prompt = self.parentConsole.prompt.clone()
                prompt.keyword = None
                self.channel.pushPromptState(prompt,False)
            else:
                self.channel.pushPromptState(prompt,True)
        else:
            self.channel.pushPromptState(self.prompt,True)

        ## don't try to get exitcode  after every sendline() call
        self._originValue = self.channel._checkExitcodeForSendline
        self.channel._checkExitcodeForSendline = False
        
        self.channel.sendlineLock.release()
        return self.returnObjectWhenEnter

    def __exit__(self,exc_type, exc_value, traceback):
        ## before exiting, we need to restore the prompt state,
        ## it makes the send() of "exit" would expect the correct prompt
        ## and we need to call _resetBuffer() for sending exitto clear the stdout and stderr buffers.
        ## for the next command to get correct stdout and stderr data in buffers.
        self.channel.sendlineLock.acquire()
        self.channel.popPromptState()
        self.channel._checkExitcodeForSendline = self._originValue
        self.channel.send(self.exit+'\n')
        self.channel.waitCommandToComplete(self.channel.waitingInterval,False)
        self.channel.getExitcode()
        ## don't need to cleanup, let user can get value of .stdout and .stderr from outer console
        #self.channel._resetBuffer()
        ## this is necessary for next command to work properly
        ## (maybe it is because that the "exit" a shell takes time)
        self.channel.wait(1)
        self.channel.sendlineLock.release()

class IterableEnterConsole(object):
    def __init__(self,parentConsole,command,stdout=None,stderr=None,exit=None):
        """
        :stdout and stderr:
            None and None: default to stdout
            False and False: default to stdout
            True and True: set type to 3 (both)
            True and None/False: set to stdout
            Non/False and True: set to stderr
        :exit:
            default to chr(3) (Ctrl-C)
        """
        assert isinstance(parentConsole,GenericConsole) 
        self.parentConsole = parentConsole
        ## self.channel is sshscript's channel
        self.channel = self.parentConsole.channel
        self.command = command
        self.queue = []
        self.type = 3 if (stdout and stderr) else (2 if stderr else 1)
        self.loopTimeout = 0
        ## default exit comand to ^C
        self.exit = exit or chr(3)
        self.returnObjectWhenEnter = self.parentConsole.returnObjectWhenEnter
    def addToQueue(self,type,lines):
        if self.type == 3:
            self.queue.append((type,lines))
        else:
            self.queue.append(lines)
    def __enter__(self):
        ## wait a moment to let  self.channel._resetBuffer() really work
        ## that we can get a clear buffer
        self.channel.sendlineLock.acquire()
        self.channel._resetBuffer()
        ## don't try to get exitcode  after every sendline() call
        self._originValue = self.channel._checkExitcodeForSendline
        self.channel._checkExitcodeForSendline = False
        self.running = True
        self.setupListener()
        self.parentConsole.send(self.command+'\n')
        return self
    def setupListener(self):
        self.channel.stdoutListener = None
        self.channel.stderrListener = None
        if self.type in (1,3):
            self.channel.stdoutListener = self.addToQueue
        if self.type in (2,3):
            self.channel.stderrListener = self.addToQueue

    def __call__(self,timeout=0):
        """
        eg.
        with $.iterate('python3 x4.py') as loopable:
            for line in loopable(timeout=3):
                ...
        """
        self.loopTimeout = timeout or 0
        return self
    def __exit__(self, exc_type, exc_value, trace):
        self.running = False
        self.channel.send(self.exit+'\n')
        self.channel.wait(1)
        self.channel.sendlineLock.release()
        self.channel._checkExitcodeForSendline = self._originValue
    def __next__(self):
        item = next(self.iter)
        return item
    def __iter__(self):
        
        def consumQueue():
            def iterTuple(item):
                for line in item[1]:
                    yield (item[0],line.decode('utf8','replace'))
            def iterList(item):
                for line in item:
                    yield line.decode('utf8','replace')
            iterator = iterTuple if self.type == 3 else iterList            
            endtime = time.time() + self.loopTimeout if self.loopTimeout else 0
            while self.running and not self.parentConsole.closed:
                n = len(self.queue)
                if n == 0:
                    if self.loopTimeout and (time.time() >= endtime):
                        raise TimeoutError(f'No data in {self.loopTimeout} seconds')
                    else:
                        time.sleep(0.1)
                        continue
                ## why lock?
                for i in range(n):
                    ## convert to str for loop's value
                    g = iterator(self.queue[i])
                    while True:
                        try:
                            yield next(g)
                        except StopIteration:
                            break
                del self.queue[0:n]
                ## reschedule endtime
                if self.loopTimeout: endtime = time.time() + self.loopTimeout
        self.iter = consumQueue()
        return self
