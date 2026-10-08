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
import math
import shlex
import uuid

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
        self.logger = self.channel.logger
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
                    self.logger.debug(
                        'Authentication prompt detected; sending password input '
                        '(length=%d)',
                        len(self.password),
                    )
                    self.channel.clear()
                    self.channel.touchIO(True)
                    self.channel.send(self.password+'\n')

                    ## reconfirm login is ok
                    #self.channel.wait_for_silent(1)
                    m = self.channel.expect([self.loginExpect,re.compile('sorry',re.I)],timeout=2,silent=True)
                    if m:
                        ## Chances is MOT like this:
                        ##    Time to change your password? Type "passwd" and follow the prompts.
                        ##		    -- Dru <genesis@istar.ca>
                        #raise PermissionError(f'"{self.loginExpect}" prompted again')
                        pass
                    else:
                        login_success = True
                else:
                    self.logger.debug(
                        'Authentication prompt was not detected; password was not sent'
                    )
            else:                
                ## has password, but no prompt have to wait
                self.logger.debug(
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
                self.logger.debug('Shell prompt detected')
            except IndexError:
                self.logger.debug('Shell prompt was not detected')
        
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

    def _finish_job(self, primary_exception):
        job = self.channel._console_job
        if job is not None:
            try:
                job.stop()
            except Exception as error:
                if primary_exception is None:
                    raise
                primary_exception.add_note('console job cleanup also raised ' + type(error).__name__)

    def exit(self,exc_type, exc_value, traceback):
        """Leave the console and restore its parent layer, applying configured exit handling."""
        
        self._finish_job(exc_value)

        ## ensure all command has sent
        #while self.channel.sending_queue.qsize() > 0: time.sleep(0.01)

        ## before sending "exit", ensure the last command has completed is important.
        ## Otherwise the "exit" could be ignored by the shell

        if self.channel._failure is not None:
            if self.channel.layer_count > 1:
                self.channel.decrease_layer()
            else:
                self.channel.on_generic_layer = True
            return False

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


class _AuthCommand(str):
    """Keep the handshake token while a generated command passes through wrappers."""
    def __new__(cls, command, auth_token):
        obj = super().__new__(cls, command)
        obj.auth_token = auth_token
        return obj


def _validate_enter_timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError('enter_timeout must be a positive finite number')
    if not math.isfinite(value) or value <= 0:
        raise ValueError('enter_timeout must be a positive finite number')
    return float(value)


def _auth_bootstrap(username, login, token):
    # Bash was already required by these consoles. Resolve it through PATH:
    # FreeBSD commonly installs it in /usr/local/bin, not /bin.
    if not isinstance(username, str) or not username or username.startswith('-'):
        raise ValueError('target username must be a nonempty name, not an option')
    if any(c in username for c in '\r\n\x00'):
        raise ValueError('invalid target username')
    script = (
        'expected=$(id -u ' + shlex.quote(username) + ') || exit 126; '
        'actual=$(id -u) || exit 126; '
        '[ "$actual" = "$expected" ] || exit 126; '
        'printf "\\n%s%s:%s:%s\\n" "__SS_AUTH_" '
        + shlex.quote(token + '__') + ' "$actual" "$$"; '
        'exec bash' + (' -i' if login else '')
    )
    # sudo -i reconstructs argv for the login shell but leaves dollar signs
    # unescaped. Encode the payload to avoid expansion by that outer shell
    # (which may be csh/tcsh). Bash's builtin printf decodes it after auth.
    encoded = ''.join(
        '\\%03o' % byte if byte in (36, 92, 96) or byte < 32 or byte >= 127
        else chr(byte) for byte in script.encode('utf-8')
    )
    decoder = 'eval "`printf %b ' + shlex.quote(encoded) + '`"'
    return 'bash -c ' + shlex.quote(decoder)


class AuthenticatedConsole(InnerConsole):
    """Enter su/sudo only after an authenticated command and identity handshake.

    A failed entry has a separate, bounded two-second recovery budget. Never
    send shell commands while an authentication conversation is unresolved.
    """
    recovery_timeout = 2.0

    def _configure_auth(self, token, enter_timeout):
        if self.password is not None and not isinstance(self.password, str):
            raise TypeError('password must be str or None')
        self.auth_token = token
        self.enter_timeout = _validate_enter_timeout(enter_timeout)
        self._executing_lock = None
        self._return_seen = False
        self._rejection_seen = False
        self._auth_identity = None
        self._command_sent = False
        self._used = False

    @staticmethod
    def _custom_command(command, bootstrap):
        if '{auth_command}' not in command and '{auth_command_quoted}' not in command:
            raise ValueError('custom console command must contain {auth_command} '
                             'or {auth_command_quoted}')
        return command.replace('{auth_command_quoted}', shlex.quote(bootstrap)).replace(
            '{auth_command}', bootstrap)

    def _remaining(self):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('console entry exceeded enter_timeout')
        return remaining

    def _line(self, kind, fields=''):
        return re.compile(
            r'(?m)^__SS_' + kind + '_' + re.escape(self.auth_token)
            + r'__' + fields + r'\r?\n'
        )

    def _emit(self, kind, arguments, fmt):
        # The full marker is absent from the input, including PTY echo.
        return ('printf "\\n%s%s' + fmt + '\\n" "__SS_' + kind + '_" '
                + shlex.quote(self.auth_token + '__') + ' ' + arguments)

    def _probe_parent(self, deadline):
        token = uuid.uuid4().hex
        command = ('printf "\\n%s%s:%s:%s\\n" "__SS_PARENT_" '
                   + shlex.quote(token + '__') + ' "$(id -u)" "$$"')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('parent shell recovery timed out')
        self.channel.send(command + '\n', timeout=remaining)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('parent shell recovery timed out')
        m = self.channel.expect(
            re.compile(r'(?m)^__SS_PARENT_' + token + r'__:(\d+):(\d+)\r?\n'),
            timeout=remaining,
        )
        return m.group(1), m.group(2)

    def enter(self):
        if self._used:
            raise RuntimeError('authenticated console contexts are single-use; create a new context')
        self._used = True
        self._deadline = time.monotonic() + self.enter_timeout
        self._parent_identity = None
        try:
            if not self.channel.on_generic_layer:
                lock = self.channel.executing_lock
                if not lock.acquire(timeout=self._remaining()):
                    raise TimeoutError('timed out acquiring parent console lock')
                self._executing_lock = lock
                self._parent_identity = self._probe_parent(self._deadline)
            if self.command:
                self.channel.clear()
                command = str(self.command)
                if self._parent_identity:
                    command = "printf '\\n'; " + command
                    command += '; ' + self._emit('RETURN', '"$?"', ':%s')
                # A failed send may have partially written the command.
                self._command_sent = True
                self.channel.send(command + '\n', timeout=self._remaining())
            else:
                # Session(..., shell=False) has already started the command.
                self._command_sent = True

            auth = self._line('AUTH', r':(\d+):(\d+)')
            returned = self._line('RETURN', r':(\d+)')
            # Narrow line-oriented rejection patterns; banners containing
            # "password" or "sorry" are not themselves authentication errors.
            rejected = re.compile(
                r'(?im)^(?:su(?:\[[^]\r\n]+\])?:\s*)?'
                r'(?:authentication failure|authentication error|'
                r'incorrect password|sorry(?:, try again\.)?)\s*\r?$'
            )
            patterns = [auth, rejected, returned]
            if self.loginExpect:
                patterns.append(self.loginExpect)
            password_sent = False
            while True:
                m = self.channel.expect(patterns, timeout=self._remaining())
                matched = getattr(m, 're', None)
                if matched is auth:
                    self._auth_identity = m.group(1), m.group(2)
                    break
                if matched is returned:
                    self._return_seen = True
                    raise RuntimeError(
                        'console command exited before readiness (status=' + m.group(1) + ')'
                    )
                if matched is rejected:
                    self._rejection_seen = True
                    raise PermissionError('console authentication was rejected')
                if password_sent:
                    raise PermissionError('authentication requested another password; no retry was sent')
                if self.password is None:
                    raise PermissionError('authentication requires a password, but none was supplied')
                self.channel.send(self.password + '\n', timeout=self._remaining())
                password_sent = True

            uid, pid = self._auth_identity
            if self._parent_identity and pid == self._parent_identity[1]:
                raise RuntimeError('authentication marker came from the parent shell')
            prompt = '_-ss_' + self.auth_token + '_'
            setup = (
                'if [ "$$" = ' + shlex.quote(pid)
                + ' ] && [ "$(id -u)" = ' + shlex.quote(uid) + ' ]; then '
            )
            if self.channel.owner.get_pty:
                setup += 'stty -echo && PS1=' + shlex.quote(prompt) + ' && '
            setup += self._emit('READY', '"$(id -u)" "$$"', ':%s:%s')
            setup += '; else ' + self._emit('BADIDENTITY', '', '') + '; fi'
            self.channel.send(setup + '\n', timeout=self._remaining())
            ready = self._line('READY', ':' + re.escape(uid) + ':' + re.escape(pid))
            bad_identity = self._line('BADIDENTITY')
            m = self.channel.expect([ready, bad_identity, returned], timeout=self._remaining())
            if m.re is returned:
                self._return_seen = True
                raise RuntimeError('target shell exited before readiness')
            if m.re is bad_identity:
                raise RuntimeError('target shell identity changed before readiness')
            if self.channel.owner.get_pty:
                self.channel.expect(re.escape(prompt), timeout=self._remaining())
            for command in self.initials or ():
                # Use an output boundary rather than waiting for silence.
                self.channel.send(command + '\n' + self._emit('INITIAL', '', '') + '\n',
                                  timeout=self._remaining())
                self.channel.expect(self._line('INITIAL'), timeout=self._remaining())
            if self.channel.on_generic_layer:
                self.channel.prompt = prompt if self.channel.owner.get_pty else None
                self.channel.on_generic_layer = False
            else:
                self.channel.increase_layer(prompt if self.channel.owner.get_pty else None)
            return self.wcw
        except BaseException:
            if self._command_sent:
                self._recover_entry()
            raise
        finally:
            # On success the parent lock remains held until context exit.
            if self._executing_lock and self._auth_identity is None:
                self._executing_lock.release()
                self._executing_lock = None

    def _recover_entry(self):
        deadline = time.monotonic() + self.recovery_timeout
        try:
            if not self._parent_identity:
                raise RuntimeError('entry has no parent shell to recover')
            if not self._return_seen:
                returned = self._line('RETURN', r':(\d+)')
                self._return_seen = any(returned.search(str(buffer)) is not None
                                        for buffer in (self.channel._stdout, self.channel._stderr))
            if not self._return_seen:
                if self._auth_identity:
                    uid, pid = self._auth_identity
                    # Authentication is over. Exit only the known target shell.
                    self.channel.send('if [ "$$" = ' + shlex.quote(pid)
                                      + ' ]; then exit; fi\n',
                                      timeout=max(0.001, deadline - time.monotonic()))
                elif self.channel.owner.get_pty and not self._rejection_seen:
                    # A reported rejection may be followed immediately by a
                    # normal exit. Interrupting that exit can cancel the parent
                    # shell command list before it emits RETURN (Bash on Linux).
                    # Let rejection reach RETURN within the recovery budget;
                    # if it keeps prompting, reject the unconfirmed channel.
                    # Raw interrupt: no newline or automatic password retry.
                    self.channel.send('\x03', timeout=max(0.001, deadline - time.monotonic()))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('console recovery timed out')
                self.channel.expect(self._line('RETURN', r':(\d+)'), timeout=remaining)
            if self._probe_parent(deadline) != self._parent_identity:
                raise RuntimeError('parent shell identity could not be restored')
        except BaseException:
            self.channel.fail(RuntimeError('console entry failed; parent shell recovery is unconfirmed'))
        finally:
            if self._executing_lock:
                self._executing_lock.release()
                self._executing_lock = None

    __enter__ = enter

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self._finish_job(exc_value)
            if self.channel._failure is not None:
                return super().__exit__(exc_type, exc_value, traceback)
            deadline = time.monotonic() + self.enter_timeout
            lock = self.channel.executing_lock
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not lock.acquire(timeout=remaining):
                raise TimeoutError('timed out acquiring target console exit lock')
            try:
                returned = self._line('RETURN', r':(\d+)')
                already_returned = bool(self._parent_identity) and any(
                    returned.search(str(buffer)) is not None
                    for buffer in (self.channel._stdout, self.channel._stderr)
                )
                if not already_returned and not self.channel._interactive_layer_exited(lock):
                    self.channel.send('exit\n', timeout=max(0.001, deadline - time.monotonic()))
                if self._parent_identity:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('console exit timed out')
                    if not already_returned:
                        self.channel.expect(returned, timeout=remaining)
                    if self._probe_parent(deadline) != self._parent_identity:
                        raise RuntimeError('parent shell identity changed on console exit')
            finally:
                lock.release()
            if self.channel.layer_count > 1:
                self.channel.decrease_layer()
            else:
                self.channel.on_generic_layer = True
            return False
        except BaseException:
            self.channel.fail(RuntimeError('console exit failed; parent shell recovery is unconfirmed'))
            if exc_value is None:
                raise
            return False
        finally:
            if self._executing_lock:
                self._executing_lock.release()
                self._executing_lock = None


class SuConsole(AuthenticatedConsole):
    """Build su commands without assuming GNU options or a /bin/bash location."""
    @classmethod
    def get_command(cls, session, username, login, get_pty, auth_token=None):
        token = auth_token or uuid.uuid4().hex
        bootstrap = _auth_bootstrap(username, login, token)
        su = r'\su' if session.connected else 'su'
        # --pty is capability-detected; BSD -c means login class before USER,
        # whereas -c after USER is passed to the user's shell. Linux/BusyBox
        # accept the latter placement too. Do not use GNU-only --login/--shell.
        args = ' --pty' if get_pty and session.is_su_pty_ok else ''
        if login:
            args += ' -'
        command = ('env LC_ALL=C LANG=C ' + su + args + ' ' + shlex.quote(username)
                   + ' -c ' + shlex.quote(bootstrap))
        return _AuthCommand(command, token)

    def __init__(self, wcw, username, password=None, expect=None, initials=None,
                 command=None, login=True, enter_timeout=10, _auth_token=None):
        _validate_enter_timeout(enter_timeout)
        token = _auth_token or getattr(command, 'auth_token', None) or uuid.uuid4().hex
        if command is None:
            command = self.get_command(wcw.channel.owner.session, username, login,
                                       wcw.channel.owner.get_pty, token)
        elif command is False:
            if _auth_token is None:
                raise ValueError('an already-started console requires its authentication token')
        elif not isinstance(command, _AuthCommand):
            bootstrap = _auth_bootstrap(username, login, token)
            command = self._custom_command(command, bootstrap)
        if expect is None:
            expect = re.compile(r'(?im)^(?:[^\r\n]*\]\s*)?password[^\r\n]*:\s*$')
        super().__init__(wcw, command, expect=expect, password=password,
                         initials=initials, exit='exit')
        self._configure_auth(token, enter_timeout)


class SudoConsole(AuthenticatedConsole):
    """Retain sudo login and sudo-to-su semantics with an authenticated bootstrap."""
    @classmethod
    def get_command(cls, session, username, login, auth_token=None):
        token = auth_token or uuid.uuid4().hex
        bootstrap = _auth_bootstrap(username or 'root', login, token)
        sudo = r'\sudo' if session.connected else 'sudo'
        command = 'env LC_ALL=C LANG=C ' + sudo + ' -k -S -p "password: "'
        if username and username != 'root':
            # Retain the existing sudo -> su policy, rather than changing it
            # to sudo -u (which would require different sudoers permissions).
            command += ' su' + (' -' if login else '') + ' ' + shlex.quote(username)
            command += ' -c ' + shlex.quote(bootstrap)
        else:
            command += (' -i' if login else '') + ' ' + bootstrap
        return _AuthCommand(command, token)

    def __init__(self, wcw, password=None, username=None, expect=None, initials=None,
                 command=None, login=True, enter_timeout=10, _auth_token=None):
        _validate_enter_timeout(enter_timeout)
        token = _auth_token or getattr(command, 'auth_token', None) or uuid.uuid4().hex
        if command is None:
            command = self.get_command(wcw.channel.owner.session, username, login, token)
        elif command is False:
            if _auth_token is None:
                raise ValueError('an already-started console requires its authentication token')
        elif not isinstance(command, _AuthCommand):
            bootstrap = _auth_bootstrap(username or 'root', login, token)
            command = self._custom_command(command, bootstrap)
        if expect is None:
            expect = re.compile(r'(?im)^(?:\[sudo\]\s*)?password[^\r\n]*:\s*$')
        super().__init__(wcw, command, expect=expect, password=password,
                         initials=initials, exit='exit')
        self._configure_auth(token, enter_timeout)


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
