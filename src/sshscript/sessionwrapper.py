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

if __package__:
    from . import patching
else:
    import patching

if __package__:
    from .errorutils import  command_is_shell
    from .channelutils import SuConsole, SudoConsole,ShellConsole,EnterConsole 
else:
    from errorutils import  command_is_shell
    from channelutils import SuConsole, SudoConsole,ShellConsole,EnterConsole

class SessionWrapper(object):
    """Operate the current console returned by shell(), su(), sudo(), or enter().

    In a shell, console(command) waits for completion and returns (stdout, stderr).
    In an enter() context, the same call sends input and waits for the program's
    prompt or exit. send() writes raw input; expect() matches buffered output.

    Nested consoles share the underlying channel. upload()/download() delegate
    to the SSH session and retain the connection account's permissions.
    """
    
    def __init__(self,console_wrapper):
        self.channel = console_wrapper.channel
        self.console_wrapper = console_wrapper
    
   
    @property
    def exitcode(self):
        ## for onedollar, the getExitcode() would be called after command
        ## but for $.enter() (EnterConsole), the getExitcode() was called by demand
        
        return self.channel.exitcode

    @property
    def stdout(self):
        """Return the current console stdout buffer; see stdio.DequeString."""
        return self.channel.stdout

    @property
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
    
    def clear(self):
        """Clear the channel's output buffers."""
        self.channel.clear()

    def send(self,s):
        """Send raw text without adding a newline; wait for the write, returning None."""
        result = self.channel.send(s)
        #result.result()
        return result

    def input(self,s,timeout=60):
        """Send a line and wait for an interactive prompt, exit, or output silence.

        Return "prompt", "exited", or "silent" in an interactive console; otherwise
        return send()'s result (None). timeout bounds the wait in seconds.
        """
        result = self.channel.input(s,timeout=timeout)
        #result.result()
        return result

    def send_line(self,s,**expections):
        """Execute a shell command and return (stdout, stderr); also console(command).

        command_timeout bounds command completion (default 60 seconds). Other keyword
        names are expected patterns and their values are reply strings.
        In an enter() context this delegates to input() and returns its status.
        """
        return self.channel.send_line(s,**expections)
    ## alias for sendline
    __call__ = send_line
    exec_command = send_line

    def expect(self,rawpat,timeout=None,stdout=True,stderr=True,silent=False):
        """Wait for an unconsumed output match; see GenericChannel.expect().

        Accept a regex string, compiled regex, callable, a list/tuple of alternatives,
        or a dict of patterns to reply strings. Return the match, successful callable,
        or completed dialog dict. timeout=None or 0 waits indefinitely; silent=True
        returns None on timeout instead of raising TimeoutError.
        """
        return self.channel.expect(rawpat,timeout,stdout,stderr,silent)

    def wait_for_silent(self,seconds,max_seconds=0):
        """Wait for seconds of output silence; return None.

        max_seconds bounds the overall wait and raises TimeoutError if exceeded;
        0 leaves it unbounded. Silence does not establish command completion.
        """
        return self.channel.wait_for_silent(seconds,max_seconds)
    wait = wait_for_silent
    def wait_for_output(self,timeout=0,silent=False):
        """Wait for new I/O activity; return True when observed.

        timeout=0 waits indefinitely. On timeout, raise TimeoutError or return False
        when silent=True. No output is consumed; see GenericChannel.wait_for_output()
        for the timestamp-based activity semantics.
        """
        return self.channel.wait_for_output(timeout,silent)

    def send_signal(self,s):
        """Send a signal.Signals value (for example signal.SIGTERM); return None."""
        return self.channel.send_signal(s)

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

    def su(self,username,password=None,expect=None,initials=None,command=None,login=True,shell=None,get_pty=None):
        """Enter a nested su console on the existing channel; see Session.su().

        initials contains setup commands. shell/get_pty are compatibility placeholders;
        they do not replace or reconfigure the existing channel.
        """
        if get_pty is not None and not isinstance(get_pty, bool):
            raise TypeError('get_pty must be None or bool')
        if command is not None and command is not False:
            if not isinstance(command, str):
                raise TypeError('command must be str, False, or None')
            if '\n' in command or '\r' in command:
                raise ValueError('persistent command must be a single line')
            command = command.strip()
            if not command:
                raise ValueError('command must not be empty')
        ## when localhost is ubuntu, pty is required for su to send password
        return SuConsole(self,username,password,expect=expect,initials=initials,command=command,login=login)
    #sudo(self,password=None,expect=None,initials=None,shell:bool=True,login=True,username=None,get_pty=True):
    def sudo(self,password,username=None,expect=None,initials=None,command=None,login=True,shell=None,get_pty=None):
        """Enter a nested sudo console on the existing channel; see Session.sudo().

        initials contains setup commands. shell/get_pty are compatibility placeholders;
        SFTP operations retain the SSH connection account's permissions.
        """
        if get_pty is not None and not isinstance(get_pty, bool):
            raise TypeError('get_pty must be None or bool')
        if command is not None and command is not False:
            if not isinstance(command, str):
                raise TypeError('command must be str, False, or None')
            if '\n' in command or '\r' in command:
                raise ValueError('persistent command must be a single line')
            command = command.strip()
            if not command:
                raise ValueError('command must not be empty')
        return SudoConsole(self,password,username=username,expect=expect,initials=initials,command=command,login=login)

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
        patching.get_thread_stack().append(self)
        return self
    ## why below??
    #enter = __enter__

    def __exit__(self,*args):
        patching.get_thread_stack().pop(self)
        return False
    def exit(self):
        return self.__exit__(None,None,None)
