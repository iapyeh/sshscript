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
import threading
import re
import __main__
import time
import os, signal

try:
    from .channelsubprocess import POpenChannel
    from .dollar import Dollar
    from .errorutils import  log_debug, log_debug_8,get_logger,EXITCODE_DEFAULT
except ImportError:
    from channelsubprocess import POpenChannel
    from dollar import Dollar
    from errorutils import log_debug, log_debug_8,get_logger,EXITCODE_DEFAULT
logger = get_logger()

class GenericConsole(object):
    """Base class for managing console contexts in SSH script.

    Provides core functionality for console operations and context management.
    """
    def __init__(self):
        """Initialize GenericConsole instance.

        Subclasses must assign returnObjectWhenEnter to specify the object
        returned when entering the console context.
        """
        ## self.returnObjectWhenEnter should be assigned by subclasses
        self.returnObjectWhenEnter = None

    '''
    ## $.su, $.sudo should push into sshscriptstack,
    ## so that $.enter() in another code block would work. eg.
    ## def enter():
    ##     with $.enter('python3'): <<== for here to work
    ##          $print("hello")
    ##  with $.sudo(..):
    ##      enter()
    def pushToStack(self):
        """Push the current console wrapper to the thread's SSH script stack.
        
        This method is used to maintain the context of nested console operations,
        allowing $.enter() to work in nested code blocks.
        """
        threading.current_thread().sshscriptstack.append(self.wcw)
    def popFromStack(self):
        """Remove the current console wrapper from the thread's SSH script stack.
        
        This method is called when exiting a console context to restore the previous
        console state.
        """
        threading.current_thread().sshscriptstack.pop(self.wcw)
    '''
class InnerConsole(GenericConsole):
    """Console implementation for inner shell operations.

    Handles shell authentication, command execution, and state management.
    """
    def __init__(self,wcw,command,expect=None,password=None,initials=None,exit=None,prompt=None):
        """Initialize InnerConsole instance.

        Args:
            wcw: The WithChannelWrapper instance that provides the channel interface
            username: The username to use for authentication
            password: Optional password for authentication
            expect: Keyword(s) to wait for when inputting password (locale-dependent)
            initials: Commands to execute after successful login, can be:
                - A shell command string
                - A list of shell commands
                - A callable function that takes the new console as argument
            command: The command to execute
        """
        ## SessionWrapper
        self.wcw = wcw

        ## instance of SSHScriptChannel
        self.channel = wcw.channel
        '''
        try:
            ## wcw.channel.owner is SessionWrapper
            self.session = wcw.channel.owner.wrapped_session
        except:
            ## wcw.channel.owner is Session
            self.session = wcw.channel.owner
        '''
        self.command = command
        self.exit_command = exit
        self.password = password
        self.loginExpect = expect
        self.initials = initials
        self.prompt = prompt
        

    def enter(self):
        """Enter the console context.
        
        This method:
        1. Sets up PTY if required
        2. Handles authentication if password is provided
        3. Executes initial commands if specified
        4. Manages the console stack
        
        Returns:
            The WithChannelWrapper instance (self.wcw)
            
        Raises:
            PermissionError: If authentication fails
        """
        if self.command:
            ## send the command to the channel, and clear the buffer to avoid mixing outputs
            self.channel.clear()
            self.channel.input(self.command)

        login_success = True
        if self.password is not None:
            ## when password is not None, we have to test if login is successful
            login_success = False 
            ## suppose password is always right
            if self.loginExpect:
                ## test if we got a prompt asking for password
                m = self.channel.expect(self.loginExpect,timeout=5,silent=True)
                if m:
                    log_debug_8(f'got {[m.group(0)]}, sending password')
                    #self.channel.wait_for_silent(1)
                    self.channel.clear()
                    self.channel.touchIO(True)
                    self.channel.send(self.password+'\n')
                    ## reconfirm login is ok
                    m = self.channel.expect(self.loginExpect,timeout=2,silent=True)
                    if m:
                        ## Chances is MOT like this:
                        ##    Time to change your password? Type "passwd" and follow the prompts.
                        ##		    -- Dru <genesis@istar.ca>
                        raise PermissionError(f'"{self.loginExpect}" prompted again')
                    login_success = True
                else:
                    log_debug_8(f'{self.loginExpect} not found, would not send password')
            else:                
                ## has password, but no prompt have to wait
                log_debug_8(f'no prompt was set, still sending password')
                self.channel.touchIO(True)
                ## when password = '', only a newline would be sent
                self.channel.send(self.password+'\n')
        if login_success:
            log_debug_8(f'login succeeded')
        else:
            log_debug_8(f'login failed, would not execute initials, and exit immediately')
            raise PermissionError('login failed')

        ## Waiting for shell's greeting to stop, guesting the prompt
        ## But for "tcpdump", "wait_for_silent(1)" could become a blocking point.
        ## So, we can set a max_seconds to avoid this blocking issue,
        ##  and still have a chance to get the prompt if the greeting is not too long.
        try:
            self.channel.wait_for_silent(1,max_seconds=3)
        except TimeoutError as e:
            pass
        else:
            try:
                user_prompt = self.channel._stdout.splitlines()[-1]
                print(f'user_prompt================>',[user_prompt])
            except IndexError:
                print(f'user_prompt====no stdout========>',[str(self.channel._stdout)])
        
        if self.initials is None:
            ## shell, su, sudo
            if self.channel.owner.get_pty:
                #prompt = '_\t%s_' % self.channel.layer_count
                #self.channel.input("tty >/dev/null 2>&1 && stty -echo && PS1=$'_\\011%s_' && echo -OKOK-" % self.channel.layer_count)
                prompt = '_-t%s_' % self.channel.layer_count
                self.channel.input("tty >/dev/null 2>&1 && stty -echo && PS1=\"_-t%s_\" && echo -OKOK-" % self.channel.layer_count)
                self.channel.expect('-OKOK-')
                ## this is very important
                self.channel.expect(prompt)
                if self.channel.on_generic_layer:
                    self.channel.prompt = prompt
                    self.channel.on_generic_layer = False
                else:
                    self.channel.increase_layer(prompt)                
            else:
                if self.channel.on_generic_layer:
                    self.channel.on_generic_layer = False
                else:
                    self.channel.increase_layer(None)
        else:
            ## enter-console
            if self.channel.on_generic_layer:
                self.channel.prompt = self.prompt
                self.channel.on_generic_layer = False
            else:
                self.channel.increase_layer(self.prompt)
        
        ## don't call reset_buffer(), otherwise first-line expect() would failed
        #self.channel.reset_buffer()        

        return self.wcw
    
    __enter__ = enter

    def exit(self,exc_type, exc_value, traceback):
        """Exit the console context.
        
        This method:
        1. Removes the console from the stack
        2. Sends exit command
        3. Restores PTY state if changed
        4. Calls exit listener if set
        
        Args:
            exc_type: The type of the exception if any
            exc_value: The value of the exception if any
            traceback: The traceback if any
        """
        
        ## ensure all command has sent
        while self.channel.sending_queue.qsize() > 0: time.sleep(0.01)

        ## before sending "exit", ensure the last command has completed is important.
        ## Otherwise the "exit" could be ignored by the shell

        if self.exit_command is not None:
            ## leaving the shell, sudo or su
            if self.channel.layer_count > 1:
                ## the su,sudo layer (above shell layer)

                ## wait current execution to complete and release locking
                self.channel.executing_lock.acquire()
                if self.channel.hijacked:
                    ## enterConsole would hijack self.channel.send_command() to self.channel.input()
                    ## and when hijacked, self.channel.input would acquire lock by itself
                    self.channel.send(self.exit_command+'\n')
                else:
                    ## 這個command一送，shell會立刻把prompt送出來，但是，會跟上層的輸出混在一起，這是一個麻煩的問題
                    #self.channel.raw_send(self.exit_command+'\n')
                    self.channel._stdout.set_callback(None,None)
                    self.channel._stderr.set_callback(None,None)
                    ## 確保最後一個指令已經沒有輸出，有助於順利結束
                    self.channel.send(self.exit_command+'\n')

                self.channel.executing_lock.release()
                self.channel.decrease_layer()
            else:
                ## the 1-level $.shell layer, or $.enter
                self.channel.on_generic_layour = True

                ## wait current execution to complete and release locking
                self.channel.executing_lock.acquire()
                if self.channel.hijacked:
                    ## enterConsole would hijack self.channel.send_command() to self.channel.input()
                    ## and when hijacked, self.channel.input would acquire lock by itself
                    self.channel.send(self.exit_command+'\n')
                else:
                    ## 這個command一送，shell會立刻把prompt送出來，但是，會跟上層的輸出混在一起，這是一個麻煩的問題
                    self.channel._stdout.set_callback(None,None)
                    self.channel._stderr.set_callback(None,None)
                    ## 確保最後一個指令已經沒有輸出，有助於順利結束
                    self.channel.send(self.exit_command+'\n')
                ## the 1-level $.shell layer, or $.enter
                self.channel.executing_lock.release()
        else:
            ## 程式會自己結束的情況(包括使用者自己輸入quit,exit)
            if self.channel.layer_count > 1:
                self.channel.decrease_layer()
            else:
                ## would end this process later
                self.channel.on_generic_layour = True
        return False
    def __exit__(self,exc_type, exc_value, traceback):
        return self.exit(exc_type, exc_value, traceback)
## with $bash, $.shell('bash')
class ShellConsole(InnerConsole):
    """Console implementation for shell commands with dollar sign syntax.

    Extends InnerConsole for dollar sign syntax commands like $bash or $.shell('bash').
    """
    def __init__(self,wcw,command,*args,**kw):
        """Initialize ShellConsole instance.

        Args:
            wcw: a SessionWrapper instance that provides the channel interface
            command: The shell command to execute
            *args: Additional positional arguments (username will be added if not provided)
            **kw: Additional keyword arguments passed to InnerConsole
            with_pty: check pty for underlying channel

        Raises:
            AssertionError: If command is not a string or starts with '#!'
        """

        if isinstance(command,str):
            command = command.strip()
    
        if 'initials' in kw:
            kw['initials'] = kw.get('initials')
            if isinstance(kw['initials'],str):
                kw['initials'] = [kw['initials']]
        else:
            kw['initials'] = None 

        kw['exit'] = kw.get('exit','exit')
        
        super().__init__(wcw,command,*args,**kw)


## v2.0.3 : ensure we have english prompt for "password", add "--prompt=password"
##          but "su" has not this argument
class SuConsole(InnerConsole):
    """Console implementation for 'su' command operations.

    This class extends InnerConsole to provide specific functionality for the 'su' command,
    including proper locale settings and prompt handling.
    """
    @classmethod
    def get_command(cls,session,username,login,get_pty):
        """
        generate the 'su' command based on connection state and where the os is bsd based
        """
        if session.connected:
            su = r'\su' ## no alias
        else:
            su = 'su' ## subprocess does not have "alias" issue
        ## if "-c bash" adding to the command end, "chr(3)" will not work as expected in $.enter()
        ## but "-c bash --pty" does.
        command = f'env LANG=en_US.UTF-8 {su} {"-" if login else ""} {username} -c "bash {"-i" if login else ""}"'
        if get_pty and session.is_su_pty_ok:
            ## Debian,Ubuntu
            command += ' --pty'
        return command

    def __init__(self,wcw,username,password=None,expect=None,initials=None,command=None,login=True):
        """Initialize SuConsole instance.

        Args:
            wcw: a SessionWrapper instance instance that provides the channel interface
            username: The username to switch to
            password: Optional password for authentication
            expect: Keyword(s) to wait for when inputting password
            initials: Commands to execute after successful login
            command: The command to execute
                None: defaults to 'LANG=en_US.UTF-8 su -l username'
                False: no command to send (see "def su" in session.py for example)
            with_pty: check pty for underlying channel
        """
        if expect is None:
            ## matching there must be a line start with "Password"
            #expect = re.compile('^\W?password',re.M|re.I)
            expect = re.compile('password',re.I)

        if command is None:
            ## default to get_pty=True
            command = SuConsole.get_command(wcw.channel.owner.session,username,login,True)
        
        super().__init__(wcw,command,expect=expect,password=password,initials=initials,exit='exit')

    
    def __enter__(self):
        if self.channel.layer_count > 1 or not self.channel.on_generic_layer:
            self.channel.executing_lock.acquire()
            self._executing_lock = self.channel.executing_lock
        else:
            self._executing_lock = None
        return super().__enter__()
    
    def __exit__(self,exc_type, exc_value, traceback):
        
        #if exc_value is not None: return False        
        
        ret = super().__exit__(exc_type, exc_value, traceback)
        if self._executing_lock:#self.channel.layer_count > 1 or not self.channel.on_generic_layer:
            #self.channel.executing_lock.release()
            ## 等久一點可以避免僅接下來的指令跟exit糾結在一起
            self.channel.wait_for_silent(2)
            self._executing_lock.release()
        
        return ret

class SudoConsole(InnerConsole):
    """Console implementation for 'sudo' command operations.

    This class extends InnerConsole to provide specific functionality for the 'sudo' command,
    including proper locale settings and prompt handling.
    """
    @classmethod
    def get_command(cls,session,username,login):
        if session.connected:
            ## prevent from executing sudo's alias
            sudo = '\\sudo' ## no alias
        else:
            sudo = 'sudo' ## subprocess does not have "alias" issue
        cmd = f"env LANG=en_US.UTF-8 {sudo} -k --stdin"            
        if username and username != 'root':
            cmd += ' su'
            ## "-" is more common than "--login"(at least works over Freebsd, MacOS, Ubuntu)
            if login: cmd += ' -'
            cmd += ' '+username
            ## call "with $.sudo(credentials[hosts[1].username],username=suUser):" in Debian/Ubuntu
            ## requires pty to show "password" prompt
            cmd += ' -c bash'
            if login: cmd += ' -' ## for bash
        else:
            if login: cmd += ' -i'
            cmd += ' bash'
            if login: cmd += ' -i' ## for bash
        logger.log(8,f'sudo command={cmd}')
        return cmd

    def __init__(self,wcw,password=None,username=None,expect=None,initials=None,command=None,login=True):
        """Initialize SudoConsole instance.

        Args:
            wcw: a SessionWrapper instance instance that provides the channel interface
            password: Optional password for sudo authentication
            expect: Keyword(s) to wait for when inputting password
            initials: Commands to execute after successful login
            command: The command to execute (defaults to 'sudo -S su' with LANG=en_US.UTF-8)
            with_pty: check pty for underlying channel
        """
        if command is None:
            command = SudoConsole.get_command(wcw.channel.owner.session,username,login)

        if expect is None:
            ## matching there must be a line start with "Password"
            ## sudo's prompt could be like this:
            ##      [sudo] password for iap
            expect = re.compile('password',re.I)

        super(SudoConsole,self).__init__(wcw,command,expect=expect,
                                         password=password,
                                         initials=initials,
                                         exit='exit')
    def __enter__(self):
        if self.channel.layer_count > 1 or not self.channel.on_generic_layer:
            self.channel.executing_lock.acquire()
            self._executing_lock = self.channel.executing_lock
        else:
            self._executing_lock = None
        return super().__enter__()
    def __exit__(self,exc_type, exc_value, traceback):
        
        #if exc_value is not None: return False
        
        ret = super().__exit__(exc_type, exc_value, traceback)
        if self._executing_lock:#self.channel.layer_count > 1 or not self.channel.on_generic_layer:
            ## 等久一點可以避免僅接下來的指令跟exit糾結在一起
            self.channel.wait_for_silent(2)
            self._executing_lock.release()
        return ret
## $.enter
class EnterConsole(InnerConsole):
    """A console implementation for handling command entry operations.
    
    This class provides functionality for entering and managing command contexts,
    including handling of input prompts and exit commands.
    """
    def __init__(self,parentConsole,command,expect=None,password=None,exit=None,prompt=None):
        """Initialize an EnterConsole instance.
        
        Args:
            parentConsole: The parent console instance (WithChannelWrapper, InnerConsoleSu, or InnerConsoleSudo)
            command: The command to execute
            expect: Pattern to wait for before sending input (e.g., "password" prompt)
            input: Value to send when expect pattern is matched (e.g., password)
            exit: Command to send when exiting:
                None: Do nothing (process will end by itself)
                chr(3): Send Ctrl+C (e.g., for tcpdump)
                'quit': Send quit command (e.g., for Python interactive console)
            with_pty: check pty for underlying channel
        """
        assert parentConsole.__class__.__name__ == __main__.SessionWrapper.__name__,f'parentConsole is {parentConsole}'

        self.parentConsole = parentConsole     
        ## self.channel is an instance of sshscriptchannel
        super(EnterConsole,self).__init__(parentConsole,command,
                                        expect=expect,
                                        password=password,
                                        initials=[],
                                        exit=exit,
                                        prompt=prompt)
        
    def __enter__(self):
        """Enter the command context.
        
        This method:
        1. Sets up PTY if required
        2. Sends the command
        3. Handles input prompts if specified
        4. Manages the console state
        
        Returns:
            The parent console instance
            
        Raises:
            TimeoutError: If expect pattern is not found within timeout
            ValueError: If command execution fails
        """
        ## wait a moment to let  self.channel._resetBuffer() really work
        ## that we can get a clear buffer
        
        if self.channel.layer_count > 1 or not self.channel.on_generic_layer:
            self._executing_lock = self.channel.executing_lock
            self._executing_lock.acquire()
        else:
            self._executing_lock = None

        super(EnterConsole,self).__enter__() 

        ## hijack sendline() to be input()
        self._restore_hijack = self.parentConsole.channel.hijack(True)
        return self.parentConsole

    def __exit__(self,exc_type, exc_value, traceback):
        """Exit the command context.
        
        This method:
        1. Sends exit command if specified
        2. Restores console state
        3. Restores PTY state if changed
        4. Updates exit code
        
        Args:
            exc_type: The type of the exception if any
            exc_value: The value of the exception if any
            traceback: The traceback if any
        """

        ret = super().__exit__(exc_type, exc_value, traceback)        
        
        if self._executing_lock:#self.channel.layer_count > 1 or not self.channel.on_generic_layer:
            ## 等久一點可以避免僅接下來的指令跟exit糾結在一起
            try:
                self.channel.wait_for_silent(2,max_seconds=3)
            except TimeoutError:
                pass
            self._executing_lock.release()

        ## restore wcw.input() to be wcw.send_line()
        if self._restore_hijack: self.parentConsole.channel.hijack(False)

        ## get this enter command's exit code, eg
        ##    with $.shell():
        ##      with $.enter('python -c ...'):
        ##            ....
        ##      assert $.exitcode == 0        <=== here, call get_exit_code to let $exitcode has value
        ## but if it is
        ##    with $.enter(...)
        ##            ...
        ##    assert $.exitcode == 0          <=== here, we do not need to call get_exit_code
        if self.parentConsole.console_wrapper.funcname in ('shell','su','sudo'):
            ## no need to get exitcode in case of exception happened
            if exc_value is None:
                self.channel.get_exit_code()

        return ret
