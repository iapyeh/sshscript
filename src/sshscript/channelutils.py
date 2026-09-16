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
"""Internal console contexts for nested shells, user switching, and interactive programs."""

import re
import time
import os, signal

if __package__:
    from .channelsubprocess import POpenChannel
    from .dollar import Dollar
    from .errorutils import get_logger, command_summary
else:
    from channelsubprocess import POpenChannel
    from dollar import Dollar
    from errorutils import get_logger, command_summary
logger = get_logger()

class GenericConsole(object):
    """Base context with a subclass-defined returnObjectWhenEnter."""
    def __init__(self):
        ## self.returnObjectWhenEnter should be assigned by subclasses
        self.returnObjectWhenEnter = None

class InnerConsole(GenericConsole):
    """Manage a nested console layer, authentication, setup commands, and exit handling."""
    def __init__(self,wcw,command,expect=None,password=None,initials=None,exit=None,prompt=None):
        """Bind a SessionWrapper to a command and its console protocol.

        expect/password handle authentication; initials supplies setup commands.
        prompt identifies readiness and exit supplies text sent on context exit.
        """
        ## SessionWrapper
        self.wcw = wcw

        ## instance of SSHScriptChannel
        self.channel = wcw.channel
        self.command = command
        self.exit_command = exit
        self.password = password
        self.loginExpect = expect
        self.prompt = prompt
        
        ## normalize self.initials (initial commands to input)
        if initials is not None:
            if isinstance(initials,str):
                self.initials = [initials]
            else:
                self.initials = initials
        else:
            self.initials = None

        

    def enter(self):
        """Enter/authenticate the console, run setup commands, and return its SessionWrapper."""
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
                    logger.debug(
                        'Authentication prompt detected; sending password input '
                        '(length=%d)',
                        len(self.password),
                    )
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
                    logger.debug(
                        'Authentication prompt was not detected; password was not sent'
                    )
            else:                
                ## has password, but no prompt have to wait
                logger.debug(
                    'No authentication prompt is configured; sending password input '
                    '(length=%d)',
                    len(self.password),
                )
                self.channel.touchIO(True)
                ## when password = '', only a newline would be sent
                self.channel.send(self.password+'\n')
        if not login_success:
            raise PermissionError(
                'Authentication failed because the password prompt was not detected'
            )

        ## Waiting for shell's greeting to stop, guesting the prompt
        ## But for "tcpdump", "wait_for_silent(1)" could become a blocking point.
        ## So, we can set a max_seconds to avoid this blocking issue,
        ##  and still have a chance to get the prompt if the greeting is not too long.
        try:
            self.channel.wait_for_silent(1,max_seconds=3)
        except TimeoutError:
            pass
        else:
            try:
                self.channel._stdout.splitlines()[-1]
                logger.debug('Shell prompt detected')
            except IndexError:
                logger.debug('Shell prompt was not detected')
        
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
            for command in self.initials:
                self.channel.input(command)
                self.channel.wait_for_silent(1)
        
        ## don't call reset_buffer(), otherwise first-line expect() would failed
        #self.channel.reset_buffer()        

        return self.wcw
    
    __enter__ = enter

    def exit(self,exc_type, exc_value, traceback):
        """Leave the console and restore its parent layer, applying configured exit handling."""
        
        ## ensure all command has sent
        #while self.channel.sending_queue.qsize() > 0: time.sleep(0.01)

        ## before sending "exit", ensure the last command has completed is important.
        ## Otherwise the "exit" could be ignored by the shell

        layer_lock = self.channel.executing_lock
        exit_command = (
            None
            if self.channel._interactive_layer_exited(layer_lock)
            else self.exit_command
        )

        if exit_command is not None:
            ## leaving the shell, sudo or su
            if self.channel.layer_count > 1:
                ## the su,sudo layer (above shell layer)

                ## wait current execution to complete and release locking
                self.channel.executing_lock.acquire()
                if self.channel.hijacked:
                    ## enterConsole would hijack self.channel.send_command() to self.channel.input()
                    ## and when hijacked, self.channel.input would acquire lock by itself
                    self.channel.send(exit_command+'\n')
                else:
                    ## 這個command一送，shell會立刻把prompt送出來，但是，會跟上層的輸出混在一起，這是一個麻煩的問題
                    #self.channel.raw_send(self.exit_command+'\n')
                    self.channel._stdout.set_callback(None,None)
                    self.channel._stderr.set_callback(None,None)
                    ## 確保最後一個指令已經沒有輸出，有助於順利結束
                    self.channel.send(exit_command+'\n')

                self.channel.executing_lock.release()
                self.channel.decrease_layer()
            else:
                ## the 1-level $.shell layer, or $.enter
                self.channel.on_generic_layer = True

                ## wait current execution to complete and release locking
                self.channel.executing_lock.acquire()
                if self.channel.hijacked:
                    ## enterConsole would hijack self.channel.send_command() to self.channel.input()
                    ## and when hijacked, self.channel.input would acquire lock by itself
                    self.channel.send(exit_command+'\n')
                else:
                    ## 這個command一送，shell會立刻把prompt送出來，但是，會跟上層的輸出混在一起，這是一個麻煩的問題
                    self.channel._stdout.set_callback(None,None)
                    self.channel._stderr.set_callback(None,None)
                    ## 確保最後一個指令已經沒有輸出，有助於順利結束
                    self.channel.send(exit_command+'\n')
                ## the 1-level $.shell layer, or $.enter
                self.channel.executing_lock.release()
        else:
            ## 程式會自己結束的情況(包括使用者自己輸入quit,exit)
            if self.channel.layer_count > 1:
                self.channel.decrease_layer()
            else:
                ## would end this process later
                self.channel.on_generic_layer = True
        return False
    def __exit__(self,exc_type, exc_value, traceback):
        return self.exit(exc_type, exc_value, traceback)
## with $bash, $.shell('bash')
class ShellConsole(InnerConsole):
    """Run a nested shell on the existing channel; constructed by SessionWrapper.shell()."""
    def __init__(self,wcw,command,*args,**kw):
        """Bind a shell command and forward console options to InnerConsole."""

        if isinstance(command,str):
            command = command.strip()
    
        kw['exit'] = kw.get('exit','exit')
        
        super().__init__(wcw,command,*args,**kw)


## v2.0.3 : ensure we have english prompt for "password", add "--prompt=password"
##          but "su" has not this argument
class SuConsole(InnerConsole):
    """Build and manage a su console with platform-specific command and prompt handling."""
    @classmethod
    def get_command(cls,session,username,login,get_pty):
        """Build the su command for this host, login mode, and PTY setting."""
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
        """Configure a su console; initials contains setup commands.

        command=None builds the default su command; command=False skips sending it
        when the underlying process was already started by Session.su().
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
    """Build and manage a sudo console with authentication and login handling."""
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
        logger.debug(
            'Built sudo command (target_user=%s, login_shell=%s)',
            username or 'root',
            login,
        )
        return cmd

    def __init__(self,wcw,password=None,username=None,expect=None,initials=None,command=None,login=True):
        """Configure sudo authentication and setup commands; see Session.sudo()."""
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
    """Temporarily route console calls to interactive input instead of shell commands.

    Entry/exit must restore the parent layer's lock and send_line binding.
    """
    def __init__(self,parentConsole,command,expect=None,password=None,exit=None,prompt=None):
        """Bind an interactive command to its parent console.

        expect/password handle authentication and prompt marks readiness. exit is
        text sent on leaving, such as "quit()" or chr(3); None sends no exit text.
        """
        if not hasattr(parentConsole, 'channel'):
            raise TypeError(
                f'parentConsole must provide a channel, not {type(parentConsole).__name__}'
            )

        self.parentConsole = parentConsole     
        ## self.channel is an instance of sshscriptchannel
        super(EnterConsole,self).__init__(parentConsole,command,
                                        expect=expect,
                                        password=password,
                                        initials=[],
                                        exit=exit,
                                        prompt=prompt)
        
    def __enter__(self):
        """Enter the program, redirect send_line to input, and return the parent console."""
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
        """Leave the program, restore command dispatch, and recover the parent shell status."""

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
