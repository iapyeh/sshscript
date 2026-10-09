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

"""Public console operations over a channel shared by shell and interactive contexts."""

import subprocess
import re
import time
import threading
from functools import wraps


def _console_operation(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        self._check_operation()
        return method(self, *args, **kwargs)
    return call

if __package__:
    from .sessionsettings import UNSET
    from . import patching
    from .commandresult import CommandResult
else:
    from sessionsettings import UNSET
    import patching
    from commandresult import CommandResult

if __package__:
    from .errorutils import  command_is_shell
    from .channelutils import SuConsole, SudoConsole,ShellConsole,EnterConsole, _AuthCommand
else:
    from errorutils import  command_is_shell
    from channelutils import SuConsole, SudoConsole,ShellConsole,EnterConsole, _AuthCommand

class SessionWrapper(object):
    """Operate the current console returned by shell(), su(), sudo(), or enter().

    In a shell, console(command) waits for completion and returns a CommandResult.
    Its text snapshots unpack as stdout, stderr, exitcode.
    In an enter() context, the same call sends input and waits for the program's
    prompt or exit. send() writes raw input; expect() matches buffered output.

    Nested consoles share the underlying channel. upload()/download() delegate
    to the SSH session and retain the connection account's permissions.
    """
    
    def __init__(self,console_wrapper):
        self.channel = console_wrapper.channel
        self.console_wrapper = console_wrapper
    
   
    @property
    @_console_operation
    def exitcode(self):
        ## for onedollar, the getExitcode() would be called after command
        ## but for $.enter() (EnterConsole), the getExitcode() was called by demand
        
        return self.channel.exitcode

    @property
    @_console_operation
    def stdout(self):
        """Return the current console stdout buffer; see stdio.DequeString."""
        return self.channel.stdout

    @property
    @_console_operation
    def stderr(self):
        """Return the current console stderr buffer; see stdio.DequeString."""
        return self.channel.stderr

    @property
    def closed(self):
        return self.channel.closed
    
    @property
    def session(self):
        """Return the owning Session; use with console.session to activate it in .spy."""
        return self

    @property
    def os_name(self):
        return self.channel.owner.session.os_name

    @property
    def local_session(self):
        return self.channel.owner.session.local_session

    @property
    def sftp(self):
        """Return the connection account's SFTP client; prefer upload()/download() for files."""
        return self.channel.owner.session.sftp
    
    @property
    def logger(self):
        """Return the session logger."""
        return self.channel.owner.session.logger
    
    def _check_operation(self):
        owner = getattr(self, '_owner_thread', None)
        if owner is not None and owner != threading.get_ident():
            raise RuntimeError('console operations must run on the thread that entered the context')
        job = getattr(self.channel, '_console_job', None)
        if job is not None and not job.done:
            raise RuntimeError('console has an active job; use job.wait() or job.stop() first')
        ensure_open = getattr(self.channel, '_raise_if_unusable', None)
        if ensure_open is not None:
            ensure_open()

    @_console_operation
    def start(self, command, *, timeout=60, stop_timeout=3,
              capture_limit=1024 * 1024, check=UNSET):
        """Start one foreground job in this shell/su/sudo context.

        Inherits cwd, environment and identity. Use its CommandJob to read/wait/stop.
        A finite total timeout is recommended; None explicitly disables it.
        Other console operations are rejected until the original shell is recovered.
        Interactive enter() contexts cannot start a shell job. PTY streams may merge.
        """
        if self.channel.hijacked:
            raise RuntimeError('start() is unavailable inside enter(); leave the interactive program first')
        if getattr(self, '_owner_thread', None) is None:
            raise RuntimeError('enter the console context before calling start()')
        if __package__:
            from .consolejob import ConsoleCommandJob
        else:
            from consolejob import ConsoleCommandJob
        session = self.channel.owner.session
        session._ensure_open()
        self.channel._raise_if_unusable()
        job = ConsoleCommandJob(self, command, timeout=timeout, stop_timeout=stop_timeout,
                                capture_limit=capture_limit,
                                check=session.check if check is UNSET else check)
        with self.channel._console_job_lock:
            if self.channel._console_job is not None:
                raise RuntimeError('console has an active job; use job.wait() or job.stop() first')
            self.channel._console_job = job
        session._jobs.add(job)
        return job._launch()

    @_console_operation
    def clear(self):
        """Clear the channel's output buffers."""
        self.channel.clear()

    @_console_operation
    def send(self,s):
        """Send raw text without adding a newline; wait for the write, returning None."""
        result = self.channel.send(s)
        #result.result()
        return result

    @_console_operation
    def input(self,s,timeout=60):
        """Send a line and wait for an interactive prompt, exit, or output silence.

        Append exactly one "\\n", even if s already ends in a newline. Use send()
        for exact text. Prefer input() for replies inside enter(); console(command)
        and send_line() keep their context-dependent behavior for compatibility.
        "silent" only reports output silence, not command success or authentication.
        Return "prompt", "exited", or "silent" in an interactive console; otherwise
        return send()'s result (None). timeout bounds the wait in seconds.
        """
        result = self.channel.input(s,timeout=timeout)
        #result.result()
        return result

    def set(self, **settings):
        """Configure the owning Session, including from $.set inside a shell."""
        self.channel.owner.session.set(**settings)

    def get(self, name=None):
        return self.channel.owner.session.get(name)

    @_console_operation
    def send_line(self,s,*,check=UNSET,**expections):
        """Execute a shell command and return CommandResult; also console(command).

        check inherits the Session policy unless explicitly supplied.
        command_timeout bounds command completion (default 60 seconds). Other keyword
        names are expected patterns and their values are reply strings.
        In an enter() context this delegates to input() and returns its status.
        This is a compatibility form, not a raw line-write API: prefer input()
        for interactive replies and send() for text without an added newline.
        """
        session = self.channel.owner.session
        enabled = session.check if check is UNSET else check
        if not isinstance(enabled, bool):
            raise TypeError('check must be bool')
        # Interactive input is not a command exit-status boundary.
        if self.channel.hijacked:
            return self.channel.send_line(s, **expections)
        settings = session.get()
        self.channel.dump2sys = (int(settings['verbose']), int(settings['verbose'] or settings['verbose_stderr']))
        self.channel.logger.settings = settings
        host = session.host
        started = time.monotonic()
        stdout, stderr = self.channel.send_line(s, **expections)
        # Snapshot before status probing can consume/replace the console buffers.
        stdout_text, stderr_text = str(stdout), str(stderr)
        status = self.channel.exitcode
        if not self.channel.prompt:
            # Pipe consoles retain the internal status marker in their live buffer.
            stdout_text = re.sub(r'_TT' + re.escape(str(status)) + r'_\r?\n?$',
                                 '', stdout_text)
        result = CommandResult(stdout_text, stderr_text, status, host,
                               time.monotonic() - started, s)
        if enabled and result.exitcode != 0:
            error = subprocess.CalledProcessError(result.exitcode, s,
                                                 output=result.stdout, stderr=result.stderr)
            error.result = result
            raise error
        return result
    ## alias for sendline
    __call__ = send_line
    exec_command = send_line

    @_console_operation
    def expect(self,rawpat,timeout=None,stdout=True,stderr=True,silent=False):
        """Wait for an unconsumed output match; see GenericChannel.expect().

        Accept a regex string, compiled regex, callable, a list/tuple of alternatives,
        or a dict of patterns to reply strings. Return the match, successful callable,
        or completed dialog dict. timeout=None or 0 waits indefinitely; silent=True
        returns None on timeout instead of raising TimeoutError.
        """
        return self.channel.expect(rawpat,timeout,stdout,stderr,silent)

    @_console_operation
    def wait_for_silent(self,seconds,max_seconds=0):
        """Wait for seconds of output silence; return None.

        max_seconds bounds the overall wait and raises TimeoutError if exceeded;
        0 leaves it unbounded. Silence does not establish command completion.
        """
        return self.channel.wait_for_silent(seconds,max_seconds)
    wait = wait_for_silent
    @_console_operation
    def wait_for_output(self,timeout=0,silent=False):
        """Wait for new I/O activity; return True when observed.

        timeout=0 waits indefinitely. On timeout, raise TimeoutError or return False
        when silent=True. No output is consumed; see GenericChannel.wait_for_output()
        for the timestamp-based activity semantics.
        """
        return self.channel.wait_for_output(timeout,silent)

    @_console_operation
    def send_signal(self,s):
        """Send a signal.Signals value (for example signal.SIGTERM); return None."""
        return self.channel.send_signal(s)

    @_console_operation
    def environ(self,key=None,value=None,**kw):
        """Update the channel's environment variables.
        
        Args:
            key (str or dict, optional): Environment variable name or dictionary of variables.
            value (str, optional): Value to set if key is a string.
            **kw: Additional keyword arguments for environment variables.
        """
        if isinstance(key,dict):
            kw.update(key)
        elif isinstance(key,str):
            kw[key] = value
        self.channel.channel.update_environment(kw)

    @_console_operation
    def su(self,username,password=None,expect=None,initials=None,command=None,login=True,shell=None,get_pty=None,enter_timeout=10,*,_auth_token=None):
        """Enter a nested su console on the existing channel; see Session.su().

        initials contains setup commands. shell/get_pty are compatibility placeholders;
        they do not replace or reconfigure the existing channel. enter_timeout
        bounds entry (default 10 seconds). Custom command templates must contain
        {auth_command} (argv) or {auth_command_quoted} (one shell argument).
        """
        if get_pty is not None and not isinstance(get_pty, bool):
            raise TypeError('get_pty must be None or bool')
        if command is not None and command is not False:
            if not isinstance(command, str):
                raise TypeError('command must be str, False, or None')
            if '\n' in command or '\r' in command:
                raise ValueError('persistent command must be a single line')
            token = getattr(command, 'auth_token', None)
            command = command.strip()
            if token:
                command = _AuthCommand(command, token)
            if not command:
                raise ValueError('command must not be empty')
        ## when localhost is ubuntu, pty is required for su to send password
        return SuConsole(self,username,password,expect=expect,initials=initials,command=command,login=login,enter_timeout=enter_timeout,_auth_token=_auth_token)
    #sudo(self,password=None,expect=None,initials=None,shell:bool=True,login=True,username=None,get_pty=True):
    @_console_operation
    def sudo(self,password=None,username=None,expect=None,initials=None,command=None,login=True,shell=None,get_pty=None,enter_timeout=10,*,_auth_token=None):
        """Enter a nested sudo console on the existing channel; see Session.sudo().

        initials contains setup commands. shell/get_pty are compatibility placeholders;
        SFTP operations retain the SSH connection account's permissions.
        enter_timeout bounds entry (default 10 seconds). Custom command templates
        must contain {auth_command} or {auth_command_quoted}; see API_GUIDE.md.
        """
        if get_pty is not None and not isinstance(get_pty, bool):
            raise TypeError('get_pty must be None or bool')
        if command is not None and command is not False:
            if not isinstance(command, str):
                raise TypeError('command must be str, False, or None')
            if '\n' in command or '\r' in command:
                raise ValueError('persistent command must be a single line')
            token = getattr(command, 'auth_token', None)
            command = command.strip()
            if token:
                command = _AuthCommand(command, token)
            if not command:
                raise ValueError('command must not be empty')
        return SudoConsole(self,password,username=username,expect=expect,initials=initials,command=command,login=login,enter_timeout=enter_timeout,_auth_token=_auth_token)

    @_console_operation
    def enter(self,command,expect=None,password=None,exit=None,shell=None,get_pty=None,prompt=None):
        """Enter an interactive program on this channel; see Session.enter().

        expect/password handle authentication; prompt marks readiness for input.
        exit is text to send on leaving (None sends nothing). shell/get_pty are
        compatibility placeholders for an already established channel.
        """
        if not isinstance(command, str):
            raise TypeError('command must be str')
        if '\n' in command or '\r' in command:
            raise ValueError('persistent command must be a single line')
        command = command.strip()
        if not command:
            raise ValueError('command must not be empty')
        if get_pty is not None and not isinstance(get_pty, bool):
            raise TypeError('get_pty must be None or bool')
        return EnterConsole(self,command,expect=expect,password=password,exit=exit,prompt=prompt)

    ## $sh      => with _sshscriptstack_[-1].shell(' sh ') 
    ## $sudo    => with _sshscriptstack_[-1].shell(' sudo ') 
    ## $python3 => with _sshscriptstack_[-1].shell(' python3 ')
    @_console_operation
    def shell(self,*args,**kw):
        """Enter a nested shell on the existing channel; return a ShellConsole context."""
        if len(args) == 0:
            command = 'bash'
        else:
            command = args[0]
            args = args[1:]

        ## ShellConsole with command=False
        if command is False:
            return ShellConsole(self,False,*args,**kw)
        if not isinstance(command, str):
            raise TypeError('command must be str or False')
        if '\n' in command or '\r' in command:
            raise ValueError('persistent command must be a single line')
        command = command.strip()
        if not command:
            raise ValueError('command must not be empty')
        if command_is_shell(command):
            ## this command is a kind of shell
            return ShellConsole(self,command,*args,**kw)
        raise ValueError(f'command "{command}" is not a shell, maybe you want to use $.enter("{command}") instead')
    def set_prompt(self,prompt):
        self.channel.prompt = prompt
        self.channel._stdout.callback_pattern = prompt
    def log(self, level, msg, *args, **kwargs):
        """Log at a standard logging level, forwarding format arguments and keywords."""
        return self.channel.log(msg, *args, level=level, **kwargs)

    ## wrappers to sshscriptsession(only those seem to be called from a "console". eg.
    ## with $.sudo() as console:
    ##      $.upload() <<-- our wrappers would be called here    
    def upload(self,*args,**kw):
        """Delegate to Session.upload(), using the SSH connection account's permissions."""
        return self.channel.owner.session.upload(*args,**kw)

    def download(self,*args,**kw):
        """Delegate to Session.download(), using the SSH connection account's permissions."""
        return self.channel.owner.session.download(*args,**kw)

    def pkey(self,*args,**kw):
        """Load an RSA private key from the session host; see Session.pkey()."""
        return self.channel.owner.session.pkey(*args,**kw)

    def onedollar(self,command,**kw):
        """Compatibility alias for exec_command()."""
        return self.exec_command(command,**kw)

    def twodollars(self,command,**kw):
        """Compatibility alias for exec_command()."""
        return self.exec_command(command,**kw)

    def __repr__(self):
        return f'SessionWrapper(id:{id(self)}, hijacked:{self.channel.hijacked})'

    def _break(self,code=0,message=''):
        self.channel.owner.session._break(code,message) 
    
    def _enter_thread(self,thread):    
        self.channel.owner.session._enter_thread(thread) 
    ## eg.
    ## with $.sudo()...
    ##     with $.session: <== here calls __enter__()
    ##        ...
    def __enter__(self):
        self._check_operation()
        self._owner_thread = threading.get_ident()
        patching.get_thread_stack().append(self)
        return self
    ## why below??
    #enter = __enter__

    def __exit__(self,*args):
        patching.get_thread_stack().pop(self)
        return False
    def exit(self):
        return self.__exit__(None,None,None)
