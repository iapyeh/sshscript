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
        self._native_id = str(threading.get_native_id())
        ## initial exitcode can not be -1,
        ## because it would trigger a calling to get the exitcode
        self._exitcode = None
        self._enter_counter = 0

        ## Guarding self._stdout, self._stderr
        self._lock = threading.Lock()
        self._stdout = SSHScriptStdout()
        self._stderr = SSHScriptStderr()
        ##lastOutputTime :最後一次有輸出的時間
        self.lastIOAtTime = [0,0] ## input(send), output(stderr,stdout)

        self._dumpCondition = threading.Condition()
        self._dumpBuf = DequeString(maxlen=1000)
        self._dumpThread = threading.Thread(target=self._dump_stdout_err_job,daemon=True,no_patch=True)
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


        self.executing_lock = threading.Lock()

        self.prefixOfLog = '[Channel]'
        self.log(f'{self} created')
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
            time.sleep(0.2)
            if time.time() - self.lastIOAtTime[0] >= seconds and\
               time.time() - self.lastIOAtTime[1] >= seconds:
                break
    ## original implementation before v2.0.3
    def wait_for_silent_with_timeout(self,seconds,timeout=0,silent=False)->bool:
        """Wait for output to be silent with an overall timeout.
        
        This method is used to determine when a command has finished executing
        by waiting for its output to stop. It will wait at least the specified
        seconds after the last output, but will timeout if output continues
        for too long.
        
        :seconds: (int)
            Wait this many seconds after the last output before returning
        :timeout: (int)
            Maximum time to wait for output to stop (0 = wait forever)
        :silent: (bool)
            If True, return False when timeout reached instead of raising exception
        :return:
            True if output became silent, False if timeout reached (silent=True)
        :raise:
            TimeoutError: if timeout reached and silent=False
        """
        self.log8(f'wait, seconds={seconds}, timeout={timeout}')
        #print(f'{id(threading.current_thread())}: wait, seconds={seconds}, timeout={timeout}')
        timeoutTime = (time.time() + timeout) if (timeout > 0) else 0
        ret = True
        while True:
            time.sleep(0.2)
            now = time.time()            
            if timeoutTime and now > timeoutTime:
                if silent:
                    ret = False
                    break
                else:
                    raise TimeoutError(f'wait exceeded {timeout}')
            elif now - self.lastOutputTime > seconds:
                break
        #print(f'{id(threading.current_thread())}: wait returns')
        return ret
    

    @property
    def stdout(self)->str:
        """Get the stdout buffer contents.
        
        If not hijacked, ensures exit code is retrieved before returning.
        
        :return: Contents of stdout buffer
        """
        if self.hijacked:
            return self._stdout
        else:    
            ## by getting exitcode, make sure we have got all the output of stdout and stderr
            if self._exitcode == EXITCODE_DEFAULT: self.get_exit_code(1)
            return self._stdout

    @property
    def stderr(self)->str:
        """Get the stderr buffer contents.
        
        If not hijacked, ensures exit code is retrieved before returning.
        
        :return: Contents of stderr buffer
        """
        if self.hijacked:
            return self._stderr
        else:
            ## by getting exitcode, make sure we have got all the output of stdout and stderr
            if self._exitcode == EXITCODE_DEFAULT: self.get_exit_code(1)
            return self._stderr

    def hijack(self,yes):
        """Hijack or release the channel's send_line method.
        
        When hijacked, send_line is replaced with input method.
        Called by EnterConsole.
        
        :yes: True to hijack, False to release
        """
        if yes:
            assert not self.hijacked,'can not hijack twice'
            assert self._send_line is None, 'can not hijack twice'
            self._send_line = self.send_line
            self.send_line = self.input
            self.hijacked = yes
            return True
        else:
            assert self.hijacked,'can not release hijack twice'
            assert self._send_line is not None, 'should release before hijacking'
            self.send_line = self._send_line
            self._send_line = None
            self.hijacked = yes
            return True
        return False

    @property
    def exitcode(self)->int:
        """Get the exit code of the last command.
        
        If exit code is -1, it will be retrieved before returning.
        
        :return: Exit code of the last command
        """
        ## v2.0.3 request by demamd
        if self._exitcode == EXITCODE_DEFAULT:
            self.get_exit_code(1)
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
        #print(f'{id(threading.current_thread())}: expect, rawpat={rawpat}, timeout={timeout}')
        ## prepare matching objects
        regularPats = []
        if not (isinstance(rawpat,list) or isinstance(rawpat,tuple)):
            rawpat = [rawpat]
        callablePats = []
        for pat in rawpat:
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
        endTime = (time.time() + timeout) if timeout else 0       
        
        def searching(items):
            for callback in callablePats:
                if callback(items):
                    return callback
            for pat in regularPats:
                m = pat.search(items[0])
                if m :
                    return m

        ret = [None]
        def listener(items):
            m = searching(items)
            if m:
                ret[0] = m
                remove_listener()

        def set_listener():
            if stdout:
                ## searching existing data
                for line in self._stdout:
                    m = searching([line])
                    if m:
                        return m
            if stderr:
                ## searching existing data
                for line in self._stderr:
                    m = searching([line])
                    if m: return m
            if stdout:
                self._stdout.push_listener(listener)
            if stderr:
                self._stderr.push_listener(listener)

        def remove_listener():
            if stdout:
                self._stdout.pop_listener(listener)
            if stderr:
                self._stderr.pop_listener(listener)

        ret[0] = set_listener()
        if ret[0] is None:
            while True:
                if ret[0] is not None:
                    break
                ## checking timeout 
                if endTime == 0:
                    pass
                elif time.time() >= endTime:
                    remove_listener()
                    if silent:
                        break
                    else:
                        raise TimeoutError(f'Not found: {rawpat}')
                time.sleep(0.25)
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
        raise   NotImplementedError('send() not implemented')

    def input(self,text):
        """Send text as input to the channel.
        
        :text: Text to send as input
        """
        self.log8(f'inputing {[text]}')
        self.send(text+'\n')

    def get_exit_code(self,timeout=None):
        """Get the exit code of the last command.
        
        :timeout: Maximum time to wait for exit code
        """
        assert not self.closed
        sno = self._increase_exitcode_sno()
        pat = self.exitcodePatterns[sno]
       
        self.wait_for_silent(0.2) ## important for stability
        self.send(f'{self._exitcodeSymbol[0]} __exitcode{sno}-_-{self._exitcodeSymbol[1]}-_-\n')
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
        self.expect(callback,timeout=timeout)
        if exitcode is not None:
            self._exitcode = exitcode

    ## run the commands
    def send_line(self,line,ensure=True):
        """Send a line or multiple lines to the channel.
        
        :line: String or list of strings to send
        """
        assert not self.hijacked, 'can not sendline when hijacked'

        return self.send_command(line,ensure=ensure)

    def send_command(self,command,ensure=True):
        """Send a command to the channel.
        
        :command: Command to execute
        :ensure: if True, request exitcode of previous execution to ensure two execution are separated
                it is for internal commands to speed up
        :return: Tuple of (stdout, stderr)
        """
        self.log8(f'executing {command}')
        '''
        :command:
            command to run, single line
        :outputTimeout: timeout of waiting io to stop,
            if outputTimeout == 0, user hints this is command won't end
            such as "tcpdump", 
        '''
        
        #command = shlex.quote(command)

        ## ensure that there is no more output, especially at the beginning when a new shell is started
        self.executing_lock.acquire()
        ## 確保跟上一個命令之間有間隔
        if ensure and self._exitcode == EXITCODE_DEFAULT:
            self.get_exit_code(2)

        ## cleanup and reset buffers of both console.stdout and console.stderr
        ## Should not depends on updateStdoutStderr(), because soon after 1st line was send, data would be received.
        ## But updateStdoutStderr() was called after the last line (so, it does not cleanup buffers)
        self.reset_buffer()
        self._exitcode = EXITCODE_DEFAULT
        ## for powershell, send \n would get \n back; send \r\n would get \r\n back
        self.send(command+'\n')        
        ## 不呼叫 self.wait()
        ## 因為不一定會有output停止的時候(eg. tcpdump會一直輸出）
        ## 但是，大部分的指令確實是有需要等一下才會有輸出。
        ## 所以，在不是with的情況下，
        #＃  如果user 讀取stdout, stderr時，如果還沒有取得exitcode，
        ##   則強制先取得exitcode

        self.executing_lock.release()
        ## v2.0.3 exitcode is requested by demand
        #return self.stdout, self.stderr, self.exitcode
        
        ## note: returned is self._stdout, not self.stdout
        ## which means, self.get_exitcode() is not called yet
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

    def _add_stdout_data(self,newbytes): 
        """Add data to stdout buffer.
        
        :newbytes: Bytes to add to stdout
        """
        ## do output, even it is empty (eg. echo $HELLO)
        #if not newbytes: return
        
        ## by checking self.closed, "exit" would not be put into stdout
        if self.closed: return
        ## when user set "encoding=utf8" for subprocess.run,newbytes is string. 
        #if isinstance(newbytes,str):
        #    newbytes = newbytes.encode()
        with self._lock:
            try:
                self._stdout.append(newbytes.decode('utf8'),True)
            except UnicodeDecodeError:
                self._stdout.append(newbytes.decode('utf8','replace'),True)
            self.touchIO(True)
            if self.dump2sys[0]:
                with self._dumpCondition:
                    self._dumpBuf.append((0,newbytes))
                    self._dumpCondition.notify()

    def _add_stderr_data(self,newbytes):
        """Add data to stderr buffer.
        
        :newbytes: Bytes to add to stderr
        """
        ## do output, even it is empty (eg. echo $HELLO)
        #if not newbytes: return
        
        ## by checking self.closed, "exit" would not be put into stdout
        if self.closed: return

        with self._lock:         
            try:
                self._stderr.append(newbytes.decode('utf8'),True)
            except UnicodeDecodeError:
                self._stderr.append(newbytes.decode('utf8','replace'),True)
            self.touchIO(True)       
            if self.dump2sys[1]:
                with self._dumpCondition:
                    self._dumpBuf.append((1,newbytes))
                    self._dumpCondition.notify()

    ## v2.0.3, adds an delegated thread to dump stdout,stderr to console
    def _dump_stderr(self,newbytes):
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

    def _dump_stdout(self,newbytes):
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

    def _dump_stdout_err_job(self):
        """Background thread function to dump stdout/stderr to console.
        
        This method runs in a separate thread and handles writing
        stdout/stderr data to the console with appropriate prefixes.
        """
        handler = [self._dump_stdout,self._dump_stderr]
        while not (self.closed or self._dumpBuf.closed):
            try:
                with self._dumpCondition:
                    while not self._dumpBuf:
                        if self._dumpCondition.wait(1):
                            break
                        elif self.closed or self._dumpBuf.closed:
                            break
                    for x,newbytes in self._dumpBuf:
                        handler[x](newbytes)
                    self._dumpBuf.clear()
            except:
                traceback.print_exc()
                break                
    
    def _dump_stdout_err(self):
        handler = [self._dump_stdout,self._dump_stderr]
        for x,newbytes in self._dumpBuf:
            handler[x](newbytes)
        self._dumpBuf.clear()
    
    def reset_buffer(self):
        """Clear stdout and stderr buffers.
        
        Also dumps buffers to screen in verbose mode.
        """
        ## clean up console.stdout, console.stderr
        ## dump to screen for verbose mode, then clean up its buffers
        with self._lock:
            #self._stdout.clear()
            #self._stderr.clear()
            self._stdout = SSHScriptStdout()
            self._stderr = SSHScriptStderr()
            self.touchIO(0)
            self.touchIO(1)
    clear = reset_buffer

    def close(self):        
        """Close the channel and cleanup resources.
        
        Ensures exit code is retrieved before closing.
        """
        assert not self.closed
        self.closed = True
        if self._dumpThread.is_alive():
            self._dumpThread.join()
        self._dumpBuf.close()
        self._stdout.close()
        self._stderr.close()

