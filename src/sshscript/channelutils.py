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


try:
    from .channelsubprocess import POpenChannel
    from .dollar import Dollar
    from .errorutils import  log_debug, log_debug_8,EXITCODE_DEFAULT
except ImportError:
    from channelsubprocess import POpenChannel
    from dollar import Dollar
    from errorutils import log_debug, log_debug_8,EXITCODE_DEFAULT

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
        print('pu' * 100)
        threading.current_thread().sshscriptstack.append(self.wcw)
    def popFromStack(self):
        """Remove the current console wrapper from the thread's SSH script stack.
        
        This method is called when exiting a console context to restore the previous
        console state.
        """
        print('pi' * 100)
        threading.current_thread().sshscriptstack.pop(self.wcw)

class InnerConsole(GenericConsole):
    """Console implementation for inner shell operations.

    Handles shell authentication, command execution, and state management.
    """
    def __init__(self,wcw,command,expect=None,password=None,initials=None,create_inner_bash=False,exit=None):
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
        ## WithChannelWrapper is inherited from GenericConsole
        ## no more assert isinstance(wcw,WithChannelWrapper), since WithChannelWrapper
        ## is not accessible in this file
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
        self.create_inner_bash = create_inner_bash
        self.returnObjectWhenEnter = self.wcw

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

        self.channel.executing_lock.acquire()
        if self.command:
            ## seprating from previous command
            if self.channel._exitcode == EXITCODE_DEFAULT:
                self.channel.get_exit_code()
            self.channel.reset_buffer()
            self.channel.input(self.command)
            
        if self.password is not None:
            ## suppose password is always right
            if self.loginExpect:
                ## test if we got a prompt asking for password
                m = self.channel.expect(self.loginExpect,timeout=5,silent=True)
                if m:
                    log_debug_8(f'got {[m.group(0)]}, sending password')
                    self.channel.clear()
                    self.channel.touchIO(True)
                    self.channel.input(self.password)
                    self.channel.wait_for_silent(1)
                    m = self.channel.expect(self.loginExpect,timeout=3,silent=True)
                    if m:
                        raise PermissionError(f'"{self.loginExpect}" prompted again')
                else:
                    log_debug_8(f'{self.loginExpect} not found, would not send password')
            else:                
                ## has password, but no prompt have to wait
                log_debug_8(f'no prompt, still sending password')
                self.channel.wait_for_silent(0.5)
                self.channel.touchIO(True)
                ## when password = '', only a newline would be sent
                self.channel.input(self.password)
                self.channel.wait_for_silent(1)

        ## create a bash shell
        if self.create_inner_bash:
            self.channel.input('bash')

        # call initials
        if isinstance(self.initials,str):
            self.channel.input(self.initials)
        elif isinstance(self.initials,list) or isinstance(self.initials,tuple):
            for command in self.initials:
                self.channel.input(command)
                self.channel.wait_for_silent(0.25)
        elif callable(self.initials):
            self.initials(self.channel)

        ## don't call reset_buffer(), otherwise first-line expect() would failed
        #self.channel.reset_buffer()        

        ## simulate executing a command,reset the exitcode and buffer
        if self.channel._exitcode is None:
            pass ## do nothing, this would let the first command not to call get_exit_code() in send_command()
        else:
            self.channel._exitcode = EXITCODE_DEFAULT ## should be "255" not "None",
        self.channel.executing_lock.release()
        return self.wcw
    
    __enter__ = enter

    def exit(self,*args):
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
        ## let next $.command not to call this console
        with self.channel.executing_lock:
            if self.create_inner_bash:
                ## leaving bash shell
                self.channel.input('exit')
                self.channel.wait_for_silent(1)
            ## leaving the sudo or su
            if self.exit_command is not None:
                self.channel.input(self.exit_command)
                self.channel.wait_for_silent(1)

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
        ## command: the shell command

        assert wcw ,f'wcw={wcw}'
        if isinstance(command,str):
            command = command.strip()
    
        if 'initials' in kw:
            kw['initials'] = kw.get('initials')
            if isinstance(kw['initials'],str):
                kw['initials'] = [kw['initials']]
        else:
            kw['initials'] = ['tty >/dev/null 2>&1 && stty -echo && PS1=\'\'']

        kw['exit'] = kw.get('exit','exit')

        kw['create_inner_bash'] = False

        super().__init__(wcw,command,*args,**kw)
        
        ## enter a shell, no need to check password
        #self.password = None
        #self.loginExpect = None

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
        command = f'env LANG=en_US.UTF-8 {su} {"-" if login else ""} {username} -c "bash -l"'
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
        log_debug_8(f'suConsole wcw.channel.with_pty={wcw.channel},{ wcw.channel.with_pty},is_su_pty_ok={wcw.channel.is_su_pty_ok}')

        if expect is None:
            expect = 'password'

        if command is None:
            ## default to get_pty=True
            command = SuConsole.get_command(wcw.channel.owner.session,username,login,True)
        
        log_debug_8(f'suConsole command={command},password={password},expect={expect},initials={initials}')
        
        if initials is None: 
            initials = ['tty >/dev/null 2>&1 && stty -echo && PS1=\'\'']


        super().__init__(wcw,command,expect=expect,password=password,initials=initials,exit='exit')

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
            if login:
                cmd += ' -'
            cmd += ' '+username
            ## call "with $.sudo(credentials[hosts[1].username],username=suUser):" in Debian/Ubuntu
            ## requires pty to show "password" prompt
            #if session.os_name in ('linux',):
            #    cmd += ' --pty'
            cmd += ' -c bash'
        else:
            if login:
                cmd += ' -i'
            cmd += ' bash'
        return cmd

    def __init__(self,wcw,password=None,expect=None,initials=None,command=None,login=True,username=None):
        """Initialize SudoConsole instance.

        Args:
            wcw: a SessionWrapper instance instance that provides the channel interface
            password: Optional password for sudo authentication
            expect: Keyword(s) to wait for when inputting password
            initials: Commands to execute after successful login
            command: The command to execute (defaults to 'sudo -S su' with LANG=en_US.UTF-8)
            with_pty: check pty for underlying channel
        """
        log_debug_8(f'sudoConsole wcw.channel.with_pty={ wcw.channel.with_pty},is_su_pty_ok={wcw.channel.is_su_pty_ok}')
       
        if command is None:
            command = SudoConsole.get_command(wcw.channel.owner.session,username,login)
        
        #if [ $? -eq 0 ]; then command2; fi
        if initials is None: 
            #initials = ['tty >/dev/null 2>&1 && stty -echo',"PS1=''"]
            initials = ['tty >/dev/null 2>&1 && stty -echo && PS1=\'\'']

        super(SudoConsole,self).__init__(wcw,command,expect=expect,
                                         password=password,
                                         initials=initials,
                                         exit='exit')

## $.enter
class EnterConsole(InnerConsole):
    """A console implementation for handling command entry operations.
    
    This class provides functionality for entering and managing command contexts,
    including handling of input prompts and exit commands.
    """
    def __init__(self,parentConsole,command,expect=None,password=None,exit=None):
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
        #assert hasattr(parentConsole,'input') and callable(parentConsole.input)
        #assert isinstance(parentConsole,__main__.SessionWrapper),f'parentConsole is {parentConsole}'
        assert parentConsole.__class__.__name__ == __main__.SessionWrapper.__name__,f'parentConsole is {parentConsole}'

        self.parentConsole = parentConsole     
        ## self.channel is an instance of sshscriptchannel
        super(EnterConsole,self).__init__(parentConsole,command,
                                        expect=expect,
                                        password=password,
                                        initials=[],
                                        create_inner_bash=False,
                                        exit=exit)        
        
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
        super(EnterConsole,self).__enter__() 
        ## prevent other execution          
        self.channel.executing_lock.acquire()
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
        ## allow super(EnterConsole,self).__exit__() to acquire

        self.channel.executing_lock.release()

        super(EnterConsole,self).__exit__(exc_type, exc_value, traceback)

        ## restore wcw.input() to be wcw.send_line()
        if self._restore_hijack: self.parentConsole.channel.hijack(False)

        ## 
        if self.channel._enter_counter > 1:
            ## set _exitcode to -1 would ensure the "channel.get_exit_code()" would be called 
            ## and make $.exitcode have value ($ might be POpenChannel instance)
            self.channel._exitcode = EXITCODE_DEFAULT
            ## don't call get_exit_code()
            ## when channel is POpen(), it has closed at __exit__()
            _ = self.channel.exitcode
        else:
            ## this is first layer $.enter, no base-shell, so can not call get_exitcode any more
            ## just pretend that it succeeded
            assert not isinstance(self.parentConsole.channel,__main__.ConsoleWrapper)
            assert  isinstance(self.parentConsole.channel.owner,Dollar),f'it is {self.parentConsole.channel.owner}'
            with_shell = self.parentConsole.channel.owner.on_top_of_shell
            print('with_shell=',with_shell)
            if isinstance(self.channel,POpenChannel):
                if with_shell:
                    self.channel.get_exit_code()
                else:
                    timeout = 10
                    while self.channel.cp.poll() is None:
                        time.sleep(1)
                        timeout -= 1
                        if timeout == 0: raise TimeoutError('Failed to get exitcode, since the process is still executing')
                    self.channel._exitcode = self.channel.cp.poll()
            else:
                if with_shell:
                    self.channel.get_exit_code()
                else:
                    timeout = 10
                    while not self.channel.channel.exit_status_ready():
                        time.sleep(1)
                        timeout -= 1
                        if timeout == 0: raise TimeoutError('Failed to get exitcode, since the process is still executing')
                    self.channel._exitcode = self.channel.channel.recv_exit_status()

            assert not self.channel._exitcode == EXITCODE_DEFAULT
            
            
            