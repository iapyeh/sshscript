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
import threading, os, sys, re
import time, traceback, shlex
import paramiko
import asyncio
try:
    from .stdio import DequeString,SSHScriptStdout,SSHScriptStderr
    #from .channelwrapper import WithChannelWrapper
    from .errorutils import  log_debug, log_debug_8,EXITCODE_DEFAULT
except ImportError:
    from stdio import DequeString,SSHScriptStdout,SSHScriptStderr
    #from channelwrapper import WithChannelWrapper
    from errorutils import  log_debug, log_debug_8,EXITCODE_DEFAULT

class GenericChannel(object):
    """Base class for channel implementations.
    
    This class provides common functionality for different channel types,
    handling stdout/stderr buffering, exit code tracking, and I/O operations.
    
    References:
    - VT100 escape sequences: https://stackoverflow.com/questions/7857352/python-regex-to-match-vt100-escape-sequences
    - Win32 non-blocking read: https://stackoverflow.com/questions/34504970/non-blocking-read-on-os-pipe-on-windows
    """
    
    ## ref: https://stackoverflow.com/questions/7857352/python-regex-to-match-vt100-escape-sequences
    ## Win32's ref: https://stackoverflow.com/questions/34504970/non-blocking-read-on-os-pipe-on-windows
    ## fish returns more complex control codes than other shells( "\n" \x0a is excluded from the following pattern)
        
    def __init__(self,owner):
        """Initialize a GenericChannel instance.
        
        :owner: The owner of this channel (typically a Dollar instance)
        """
        self._native_id = str(int(time.time()))
        ## initial exitcode can not be -1,
        ## because it would trigger a calling to get the exitcode
        self._exitcode = None
        self._enter_counter = 0

        ## Guarding self._stdout, self._stderr
        self._lock = asyncio.Lock()
        #self._stdout = SSHScriptStdout()
        #self._stderr = SSHScriptStderr()
        ##lastOutputTime :最後一次有輸出的時間
        self.lastIOAtTime = [time.time(),time.time()] ## input(send), output(stderr,stdout)

        ## this is for onedollar and twodollar
        self._dumpCondition = asyncio.Condition()
        #self._dumpCondition = None
        #self._dumpBuf = DequeString(maxlen=1000)
        self._dumpBuf = []
        self._stdoutDumpBuf = b''
        self._stderrDumpBuf = b''
        
        ## an instance of Dollar
        self.owner = owner

        ## see hijack() for details
        self.hijacked = False
        self._send_line = None
        
        ## set default value for PopenChannel and SSHChannel
        self.with_pty = None

        ## 確保跟上一個命令之間有間隔的方式：
        ## 執行命令之前(sendcommand)，檢查上一個命令是否有取得exitcode，
        ## 如果沒有，則送出一個dumyEcho
        #self._exitcode_session_id = 0
        #self._command_session_id = 0
        if os.environ.get('VERBOSE'):
            ## verbose-related
            self.dump2sys = (1,1)
            self.stdoutPrefix = os.environ.get('VERBOSE_STDOUT_PREFIX','🟩').encode('utf8')
            self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','🟨').encode('utf8')
        elif os.environ.get('VERBOSE_STDERR'):
            self.dump2sys = (0,1)
            self.stdoutPrefix = b''
            self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','🟨').encode('utf8')
        else:
            self.dump2sys = (0,0)
            self.stderrPrefix = b''
            self.stdoutPrefix = b''
        
        self.closed = False
        self.withChannelWrapper = None
        
        ## mostly is $? for bash, sh, zsh, but it is "$status" for fish
        self._exitcodeSymbol = ('echo','$?')

        ## rotate the command to ask for exitcode, this is for preventing from falsely got previous exitcode
        self._exitcodeSno = 0
        self.exitcodePatterns = []
        self._exitcode_command_pat = re.compile(f'(\\W?)echo __exitcode\\d+\\-_\\-\\$\\?\\-_\\-\\r?\\n?',re.S)
        for sno in range(30):
            pat = re.compile(f'(\\W?)(?:echo )?__exitcode{sno}\\-_\\-(\\d+)\\-_\\-\\r?\\n?',re.M)
            self.exitcodePatterns.append(pat)

        ## layer's variable
        self.executing_locks = []
        self.prompts= []
        self.stdio_store = []

        self.prefixOfLog = '[Channel]'

        self.sending_queue = asyncio.Queue()
        self.expecting_queue = asyncio.Queue()

        ## initailly set layer 1
        self.increase_layer('')
        ## this flag control $.shell to use existing layer or increase layer
        self.on_generic_layer = True 

    @property
    def executing_lock(self):
        return self.executing_locks[-1]
    @property
    def prompt(self):
        return self.prompts[-1]
    @prompt.setter
    def prompt(self,text):
        self.prompts[-1] = text
    @property
    def _stdout(self):
        return self.stdio_store[-1][0]            
    @property
    def _stderr(self):
        return self.stdio_store[-1][1]
    @property
    def layer_count(self):
        return len(self.stdio_store)
    def increase_layer(self,prompt):
        ## clone the current _stdout, stderr
        ## there are the message of shell, su or sudo, and important
        ## there also having "password:" prompt, it would be the targets for expect()
        if len(self.stdio_store):
            self.stdio_store.append([SSHScriptStdout(self._stdout),SSHScriptStderr(self._stderr)])
        else:
            self.stdio_store.append([SSHScriptStdout(),SSHScriptStderr()])
        self.prompts.append(prompt)
        self.executing_locks.append(threading.Lock())
    def decrease_layer(self):
        ## keep at least one layer
        assert self.layer_count > 1
        self.prompts.pop()
        self.executing_locks.pop()
        self.stdio_store.pop()
    
    def _increase_exitcode_sno(self):
        """Increment the exit code sequence number.
        
        :return: The new sequence number (0-29)
        """
        self._exitcodeSno = (self._exitcodeSno + 1) % 30
        return self._exitcodeSno

    @property
    def is_su_pty_ok(self):
        return self.owner.session.is_su_pty_ok
    @property
    def os_name(self):
        return self.owner.session.os_name
    
    @property
    def lastOutputTime(self):
        """Get the timestamp of the last output.
        
        :return: Timestamp of the last output
        """
        return self.lastIOAtTime[1]
    
    
    def touchIO(self,isOutput):
        """Update the I/O timestamps.
        
        :isOutput: True if this is an output operation, False for input
        """
        if isOutput:
            self.lastIOAtTime[1] = time.time()
        else:
            ## sending command, also reset output time
            self.lastIOAtTime[0] = self.lastIOAtTime[1] = time.time()

    ## v2.0.3 redefined
    def wait_for_output(self,timeout=0,silent=False)->bool:
        """Block execution until stdout or stderr received or timeout reached.
        
        :timeout: (int)
            0: waiting forever
        :silent: (bool)
            if True, return False when timeout reached
        :return:
            True: has output
            False: timeout(silent=True)
        :raise:
            TimeoutError: timeout(silent=False)
        """
        basetime = self.lastIOAtTime[:]
        timeouttime = (time.time() + timeout) if timeout else 0
        ret = True
        self.log8(f'{id(threading.current_thread())}: wait_for_output, timeout={timeout},timeouttime={timeouttime}')
        count = 0
        while True:
            time.sleep(0.2)
            if self.lastIOAtTime[0] != basetime[0] or \
                self.lastIOAtTime[1] != basetime[1]:
                break
            elif timeouttime and time.time() > timeouttime:
                if silent:
                    ret = False
                    break
                else:
                    raise TimeoutError(f'wait_for_output exceeded {timeout}')
            else:
                count += 1
                if count % 20 == 0:
                    self.log8(f'{id(threading.current_thread())}: wait_for_output waiting, count = {count}')

        self.log8(f'{id(threading.current_thread())}: wait_for_output complete, timeout={timeout}')
        return ret
    ## v2.0.3 redefined
    def wait_for_silent(self,seconds)->bool:
        """Block execution until output is silent for the specified duration.
        
        If output continues (e.g., from tcpdump), it will block until output stops.
        
        :seconds: (int)
            Wait this many seconds after the last output before returning
        """
       
        while True:
            now = time.time()
            if now - self.lastIOAtTime[0] >= seconds and\
               now - self.lastIOAtTime[1] >= seconds:
                break
            time.sleep(0.1)

    ## v3.0
    def wait_for_prompt(self,prompt,timeout=None)->bool:
        """Block execution until output is silent for the specified duration.
        
        If output continues (e.g., from tcpdump), it will block until output stops.
        
        :seconds: (int)
            Wait this many seconds after the last output before returning
        """
        self.expect(prompt,timeout=timeout)

    @property
    def stdout(self)->str:
        """Get the stdout buffer contents.
        
        If not hijacked, ensures exit code is retrieved before returning.
        
        :return: Contents of stdout buffer
        """
        if self.hijacked:
            with self.executing_lock:
                return self._stdout
        else:    
            ## by getting exitcode, make sure we have got all the output of stdout and stderr
            #if self._exitcode == EXITCODE_DEFAULT: self.get_exit_code()
            with self.executing_lock:
                return self._stdout


    @property
    def stderr(self)->str:
        """Get the stderr buffer contents.
        
        If not hijacked, ensures exit code is retrieved before returning.
        
        :return: Contents of stderr buffer
        """
        if self.hijacked:
            with self.executing_lock:
                return self._stderr
        else:
            ## by getting exitcode, make sure we have got all the output of stdout and stderr
            #if self._exitcode == EXITCODE_DEFAULT: self.get_exit_code(1)
            with self.executing_lock:
                return self._stderr

    def hijack(self,yes):
        """
        Called by EnterConsole.       
        Hijack or release the channel's send_line method.
        
        When hijacked
        1. send_line is replaced with input method.
        2. no exitcode 
        
        :yes: True to hijack, False to release
        """
        if yes:
            assert not self.hijacked,'can not hijack twice'
            assert self._send_line is None, 'can not hijack twice'
            self._send_line = self.send_line
            self.hijacked = True
            self.send_line = self.input
            return True
        else:
            assert self.hijacked,'can not release hijack twice'
            assert self._send_line is not None, 'should release before hijacking'
            self.send_line = self._send_line
            self._send_line = None
            self.hijacked = False
            return True
        return False

    @property
    def exitcode(self)->int:
        """Get the exit code of the last command.
        
        If exit code is -1, it will be retrieved before returning.
        
        :return: Exit code of the last command
        """
        if self.hijacked:
            raise ValueError('exitcode is not available in current state')
        ## v2.0.3 request by demamd
        if self._exitcode == EXITCODE_DEFAULT:
            return self.get_exit_code()
        else:
            return self._exitcode

    def log(self,msg, *args):
        """Log a debug message.
        
        :msg: Message to log
        :*args: Additional arguments for formatting
        """
        log_debug(f'{self.prefixOfLog}{msg}', *args)

    def log8(self,msg, *args):
        """Log a debug message with level 8.
        
        :msg: Message to log
        :*args: Additional arguments for formatting
        """
        log_debug_8(f'T{self._native_id}:{self.prefixOfLog}{msg}', *args)

    def expect(self,rawpat,timeout=None,stdout=True,stderr=True,silent=False):
        """Block until a pattern is matched in output or timeout reached.
        
        This is a blocking function that waits for a pattern to appear in
        stdout or stderr. the searching target can not across lines.
        
        :rawpat:
            - bytes,str,re.Pattern or list of them
            if re.Pattern is given, it should match bytes (starts from v2.0.3)
            - callable , eg:
                def callback(buf, pos):
                    if '__exitcode0_' in buf[pos]:
                        ## stop the expect() call
                        return True
        :timeout:
            0 or None: waiting forever
        :stdout: Whether to search in stdout
        :stderr: Whether to search in stderr
        :silent:
            if False, raise TimeoutError when timeout 
            if True, raise nothing, just return False when timeout
        :return:
            Match object or callback result if pattern found
            False if timeout and silent=True
        :raise:
            TimeoutError: if timeout reached and silent=False
        """

        ## prepare matching objects
        regularPats = []
        if isinstance(rawpat,dict):
            rawpat = dict(zip([x.lower() for x in rawpat.keys()],rawpat.values()))
            pats = list(rawpat.keys())
        elif (isinstance(rawpat,list) or isinstance(rawpat,tuple)):
            pats = rawpat
        else:
            pats = [rawpat]
        callablePats = []
        for pat in pats:
            if isinstance(pat,str):
                regularPats.append(re.compile(pat,re.I))
            elif isinstance(pat,bytes):
                regularPats.append(re.compile(pat.decode('utf8'),re.I))
            elif callable(pat):
                callablePats.append(pat)
            elif isinstance(pat,re.Pattern):
                assert isinstance(pat.pattern,str),f'expect() should be called with str-pattern, not "{pat.pattern}"'
                regularPats.append(pat)
            else:
                raise ValueError('expect() only accept bytes,str,re.Pattern(str) or list of them')
        ## comparing starts
        def searching(items):
            for callback in callablePats:
                if callback(items):
                    return callback
            for pat in regularPats:
                m = pat.search(items[0])
                if m :
                    return m
        
        ret = [None]
        listener_pushed = False
        def found(m):
            nonlocal regularPats
            if isinstance(rawpat,dict):
                if ret[0] is None:
                    ret[0] = m
                else:
                    ret.append(m)
                self.raw_send(rawpat[m.group(0).lower()]+'\n')
                self.wait_for_silent(1)
                del rawpat[m.group(0).lower()]
                if len(rawpat) == 0:
                    remove_listener()
                else:
                    ## update pattern
                    regularPats = [re.compile(x,re.I) for x in rawpat.keys()]
            else:
                ret[0] = m
                remove_listener()

        def listener(items)->bool:
            """ return True if completed"""
            nonlocal regularPats
            m = searching(items)
            if m is None: return 
            found(m)
            if isinstance(rawpat,dict):
                if len(rawpat) == 0:
                    return True
            else:
                return True

        def set_listener()->bool:
            nonlocal listener_pushed
            """ return True if completed"""

            ## searching existing buffer
            if stdout:
                for line in self._stdout.splitlines():
                    if listener([line]): return True                           
            
            if stderr:
                ## searching existing data
                for line in self._stderr.splitlines():
                    if listener([line]): return True
            
            if stdout:
                self._stdout.push_listener(listener)
            if stderr:
                self._stderr.push_listener(listener)
            listener_pushed = True
        
        def remove_listener():
            nonlocal listener_pushed
            if listener_pushed:
                if stdout:
                    self._stdout.pop_listener(listener)
                if stderr:
                    self._stderr.pop_listener(listener)
        
        ## waiting for pattern shows up
        endTime = (time.time() + timeout) if timeout else 0       
        if not set_listener():
            while True:
                if isinstance(rawpat,dict):
                    if len(rawpat) == 0:
                        break
                elif ret[0] is not None:
                    break
                ## checking timeout 
                elif endTime == 0:
                    pass
                elif time.time() >= endTime:
                    remove_listener()
                    if silent:
                        break
                    else:
                        raise TimeoutError(f'Not found: {rawpat}')
                time.sleep(0.1)
                #await asyncio.sleep(0.1)
        #print(f'->expect returns {ret}')
        #asyncio.get_event_loop().stop()
        if isinstance(rawpat,dict):
            return ret
        else:
            return ret[0]

    def __enter__(self):
        self._enter_counter += 1
    
    def __exit__(self,exc_type, exc_value, traceback):
        ## when exception was raised, this channel could be closed already
        ## so, do nothing when it happens
        self._enter_counter -= 1
        assert self._enter_counter >= 0
        if self._enter_counter == 0:
            self.close()
    
    def send(self,text):
        self.sending_queue.put_nowait(text)

    def raw_send(self,text):
        raise   NotImplementedError('raw_send() not implemented')

    async def _start_interaction(self):
        ## miso
        await asyncio.gather(self._start_reading(),self.consume_sending_queue(),self._dump_stdout_err_job())#,self.consume_expecting_queue())
    def start_interaction(self):
        def r():
            newloop = asyncio.new_event_loop()
            self.interaction_loop = newloop
            asyncio.set_event_loop(newloop)
            ## create another new Condition for this event loop
            self._dumpCondition = asyncio.Condition()
            if hasattr(asyncio, "get_child_watcher"):
                watcher = asyncio.get_child_watcher()
                watcher.attach_loop(newloop)
            task = newloop.create_task(self._start_interaction())
            try:
                newloop.run_forever()
            except Exception as e:
                traceback.print_exc()
            finally:
                task.cancel()
                newloop.run_until_complete(newloop.shutdown_default_executor())
                newloop.run_until_complete(newloop.shutdown_asyncgens())
                if hasattr(asyncio, "get_child_watcher"):                
                    try:
                        watcher.attach_loop(None)
                    except: pass 
                newloop.close()
                asyncio.set_event_loop(None)
        self.interaction_thread = threading.Thread(target=r,daemon=True,name='expect.call')
        self.interaction_thread.start()
    async def consume_sending_queue(self):
        empty = asyncio.queues.QueueEmpty
        while not self.closed:
            try:
                text = self.sending_queue.get_nowait()
            except empty:
                await asyncio.sleep(0.1)
            else:
                try:
                    self.raw_send(text)
                except OSError:
                    ## eg. socket closed
                    self.log('failure to send')
                    traceback.print_exc()
                    raise
                else:
                    ## let other coroutine has chances to work
                    ## this is important
                    await asyncio.sleep(0.1)
        #self.sending_queue.join()
    async def consume_expecting_queue(self):
        empty = asyncio.queues.QueueEmpty
        self._expect_ret = None
        while not self.closed:
            try:
                args = self.expecting_queue.get_nowait()
            except empty:
                await asyncio.sleep(0.1)
                
            else:
                self._expect_ret = None
                try:
                    self._expect_ret = await self.aexpect(*args)
                    print('self._expect_ret==',self._expect_ret)
                except OSError:
                    ## eg. socket closed
                    traceback.print_exc()
                    raise
                else:
                    self.expecting_queue.task_done()
        #self.expecting_queue.join()
    def input(self,text):
        """Send text as input to the channel.
        
        :text: Text to send as input
        """
        self.log8(f'inputing {[text]}')

        if self.hijacked:
            ## caution: if user's last command is "exit", this lock would not be release
            ##      but it does not matter, becuase that layer would be removed as well as this lock
            self.executing_lock.acquire()
            if self.prompt:
                self.reset_buffer()
                def prompt_found_callback():
                    self.executing_lock.release()
                self._stdout.set_callback(prompt_found_callback,self.prompt)
                self._stderr.set_callback(prompt_found_callback,self.prompt)
        self.send(text+'\n')
        if self.hijacked and not self.prompt:
            ## when inputing password
            self.wait_for_silent(1)
            self.executing_lock.release()

    def get_exit_code(self,timeout=None):
        """Get the exit code of the last command.
        
        :timeout: Maximum time to wait for exit code
        """
        
        assert not self.closed
       
        ## important for stability
        with self.executing_lock:
            #self.wait_for_silent(1)
            sno = self._increase_exitcode_sno()
            pat = self.exitcodePatterns[sno]
            #_stdout = self._stdout
            #_stderr = self._stderr
            _backup_stdio = self.stdio_store[-1][:]
            self.reset_buffer()
            
            complete = False
            def prompt_found_callback():
                nonlocal complete
                m = pat.search(str(self._stdout))
                if m:
                    self._exitcode = int(m.group(2))
                    #self._stdout = _stdout
                    #self._stderr = _stderr
                else:
                    m = pat.search(str(self._stderr))
                    if m:
                        self._exitcode = int(m.group(2))
                        #self._stdout = _stdout
                        #self._stderr = _stderr
                self.stdio_store[-1] = _backup_stdio
                complete = True
                #self.executing_lock.release()
            self._stdout.set_callback(prompt_found_callback,self.prompt)
            self._stderr.set_callback(prompt_found_callback,self.prompt)
            self.send(f'{self._exitcodeSymbol[0]} __exitcode{sno}-_-{self._exitcodeSymbol[1]}-_-\n')
            while not complete:
                time.sleep(0.1)
            return self._exitcode
        '''
        exitcode = None
        def callback(items):
            nonlocal exitcode
            m = pat.search(items[0])
            if m:
                exitcode = int(m.group(2))
                items[0] = self._exitcode_command_pat.sub(r'\1', pat.sub(r'\1',items[0]))
                return True
            ## note: self._exitcode_command_pat string might appear on stderr
            ## when not setting PS1=""
        await self.expect(callback,timeout=timeout)
        if exitcode is not None:
            self._exitcode = exitcode
        '''
    ## run the commands
    def send_line(self,line,**expections):
        """Send a line or multiple lines to the channel.
        
        :line: String or list of strings to send
        """
        assert not self.hijacked, 'can not sendline when hijacked'

        return self.send_command(line,**expections)

    def send_command(self,command,**expections):
        """Send a command to the channel.       
        :command: Command to execute
        :expections: expecting and inputing, eg.

        :return: Tuple of (stdout, stderr)
        """
        self.log8(f'send_command: {command},prompt={self.prompt},self._exitcode={self._exitcode}')
        
        ## ensure that there is no more output, especially at the beginning when a new shell is started
        self.executing_lock.acquire()
        self._exitcode = EXITCODE_DEFAULT
        self.reset_buffer()
        if len(expections)==0:
            if self.prompt:
                def prompt_found_callback():
                    self.executing_lock.release()
                self._stdout.set_callback(prompt_found_callback,self.prompt)
                self._stderr.set_callback(prompt_found_callback,self.prompt)
        ## for powershell, send \n would get \n back; send \r\n would get \r\n back
        self.send(command+'\n')
        if len(expections):
            lowerkey_expections = dict(zip([x.lower() for x in expections.keys()],expections.values()))
            while len(lowerkey_expections):
                m = self.expect(list(lowerkey_expections.keys()),timeout=60)
                self.input(lowerkey_expections[m.group(0).lower()])
                del lowerkey_expections[m.group(0).lower()]
            if self.prompt:
                def prompt_found_callback():
                    self.executing_lock.release()
                self._stdout.set_callback(prompt_found_callback,self.prompt)
                self._stderr.set_callback(prompt_found_callback,self.prompt)
            else:
                self.wait_for_silent(1)
                self.executing_lock.release()
        return self._stdout, self._stderr
   
    def send_signal(self,sig):
        """Send a signal to the process.
        
        :sig: Signal to send
        """
        if isinstance(self,__main__.SSHChannel):
            message = paramiko.Message()
            message.add_byte(paramiko.common.cMSG_CHANNEL_REQUEST)
            message.add_int(self.channel.channel.remote_chanid)
            message.add_string("signal")
            message.add_boolean(False)
            message.add_string(sig.name[3:])
            #message.add_string('TERM')
            self.channel.channel.transport._send_user_message(message) 
        else:
            self.cp.send_signal(sig)

    async def _add_stdout_data(self,newbytes): 
        """Add data to stdout buffer.
        
        :newbytes: Bytes to add to stdout
        """
        self.touchIO(True)
        ## do output, even it is empty (eg. echo $HELLO)
        #if not newbytes: return

        ## by checking self.closed, "exit" would not be put into stdout
        if self.closed: return
        ## when user set "encoding=utf8" for subprocess.run,newbytes is string. 
        #if isinstance(newbytes,str):
        #    newbytes = newbytes.encode()
        async with self._lock:
            try:
                self._stdout.append(newbytes.decode('utf8'),True)
            except UnicodeDecodeError:
                self._stdout.append(newbytes.decode('utf8','replace'),True)
            if self.dump2sys[0]:
                async with self._dumpCondition:
                    self._dumpBuf.append((0,newbytes))
                    self._dumpCondition.notify()

    async def _add_stderr_data(self,newbytes):
        """Add data to stderr buffer.
        
        :newbytes: Bytes to add to stderr
        """
        ## do output, even it is empty (eg. echo $HELLO)
        #if not newbytes: return
        self.touchIO(True)
        ## by checking self.closed, "exit" would not be put into stdout
        if self.closed: return

        async with self._lock:         
            try:
                self._stderr.append(newbytes.decode('utf8'),True)
            except UnicodeDecodeError:
                self._stderr.append(newbytes.decode('utf8','replace'),True)
            if self.dump2sys[1]:
                async with self._dumpCondition:
                    self._dumpBuf.append((1,newbytes))
                    self._dumpCondition.notify()

    ## v2.0.3, adds an delegated thread to dump stdout,stderr to console
    async def _dump_stderr(self,newbytes):
        try:
            p = newbytes.rindex(b'\n')
        except ValueError:
            self._stderrDumpBuf += newbytes
        else:
            content = self._stderrDumpBuf + newbytes[:p]
            for line in content.splitlines():
                sys.stderr.buffer.write(self.stderrPrefix+self._native_id.encode()+b':'+line+b'\n')
            self._stderrDumpBuf = newbytes[p+1:]
            sys.stderr.buffer.flush()        

    async def _dump_stdout(self,newbytes):
        ''' print to console line by line, no print if no new line'''
        try:
            p = newbytes.rindex(b'\n')
        except ValueError:
            self._stdoutDumpBuf += newbytes
        else:
            content = self._stdoutDumpBuf + newbytes[:p]
            for line in content.splitlines():
                sys.stdout.buffer.write(self.stdoutPrefix+self._native_id.encode()+b':'+line+b'\n')
            self._stdoutDumpBuf = newbytes[p+1:]
            sys.stdout.buffer.flush()

    async def _dump_stdout_err_job(self):
        """Background thread function to dump stdout/stderr to console.
        
        This method runs in a separate thread and handles writing
        stdout/stderr data to the console with appropriate prefixes.
        """
        handler = [self._dump_stdout,self._dump_stderr]
        #while not (self.closed or self._dumpBuf.closed):
        while not self.closed:
            try:
                async with self._dumpCondition:
                    if self.closed: break
                    try:
                        #await asyncio.wait_for(self._dumpCondition.wait(),timeout=0.1)
                        #newloop.run_until_complete(self._start_interaction())
                        await self._dumpCondition.wait()
                    except (asyncio.exceptions.CancelledError,GeneratorExit):
                        break
                    except asyncio.exceptions.TimeoutError:
                        if self.closed:# or self._dumpBuf.closed:
                            break
                        else:
                            try:
                                ## important for avoiding blocking the event loop
                                await asyncio.sleep(0.01)
                            except asyncio.exceptions.CancelledError:
                                break                            
                    else:
                        for x,newbytes in self._dumpBuf:
                            await handler[x](newbytes)
                        self._dumpBuf.clear()
            except:
                traceback.print_exc()
                break
    async def _dump_stdout_err(self):
        handler = [self._dump_stdout,self._dump_stderr]
        for x,newbytes in self._dumpBuf:
            await handler[x](newbytes)
        self._dumpBuf.clear()
    
    def reset_buffer(self):
        """Clear stdout and stderr buffers.
        
        Also dumps buffers to screen in verbose mode.
        """
        ## clean up console.stdout, console.stderr
        ## dump to screen for verbose mode, then clean up its buffers
        self.stdio_store[-1][0] = SSHScriptStdout()
        self.stdio_store[-1][1] = SSHScriptStderr()
        self.touchIO(0)
        self.touchIO(1)
    clear = reset_buffer

    def close(self):        
        """Close the channel and cleanup resources.
        
        Ensures exit code is retrieved before closing.
        """
        assert not self.closed
        self.closed = True
        #self._dumpBuf.close()
        self._stdout.close()
        self._stderr.close()
        #self.owner.event_loop.stop()

