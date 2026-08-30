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

import __main__, threading

if __package__:
    from .errorutils import  command_is_shell
    from .channelutils import SuConsole, SudoConsole,ShellConsole,EnterConsole 
else:
    from errorutils import  command_is_shell
    from channelutils import SuConsole, SudoConsole,ShellConsole,EnterConsole

class SessionWrapper(object):
    """
    A wrapper class for SSH channels that provides enhanced functionality and convenience methods.
    
    This class wraps a channel object and provides additional methods for interacting with
    SSH sessions, including command execution, environment management, and file transfers.
    
    """
    
    def __init__(self,console_wrapper):
        """Initialize the channel wrapper.
        
        Args:
            channel: The underlying channel object to wrap.
        """
        self.channel = console_wrapper.channel
        self.console_wrapper = console_wrapper
    
   
    @property
    def exitcode(self):
        ## for onedollar, the getExitcode() would be called after command
        ## but for $.enter() (EnterConsole), the getExitcode() was called by demand
        
        return self.channel.exitcode

    @property
    def stdout(self):
        """Get the standard output from the channel.
        
        Returns:
            str: The standard output content.
        """
        return self.channel.stdout

    @property
    def stderr(self):
        """Get the standard error from the channel.
        
        Returns:
            str: The standard error content.
        """
        return self.channel.stderr

    @property
    def closed(self):
        """Check if the channel is closed.
        
        Returns:
            bool: True if the channel is closed, False otherwise.
        """
        return self.channel.closed
    
    @property
    def session(self):
        """Get the underlying SSH session.
            use case:
                with $.session: <== here
                    ...
        Returns:
            Session: The SSH session object.
        """
        return self

    @property
    def os_name(self):
        return self.channel.owner.session.os_name

    @property
    def local_session(self):
        return self.channel.owner.session.local_session

    @property
    def sftp(self):
        """Get the SFTP client associated with the session.
        
        Returns:
            SFTPClient: The SFTP client object.
        """
        return self.channel.owner.session.sftp
    
    @property
    def logger(self):
        """Get the logger associated with the session.
        
        Returns:
            Logger: The logger object.
        """
        return self.channel.owner.session.logger
    
    def clear(self):
        """Clear the channel's output buffers."""
        self.channel.clear()

    def send(self,s):
        """Send data to the channel.
        
        Args:
            s (str): The data to send.
            
        Returns:
            int: The number of bytes sent.
        """
        result = self.channel.send(s)
        #result.result()
        return result

    def input(self,s,timeout=60):
        """Send input and wait for the prompt or console exit.
        
        Args:
            s (str): The input to send.
            timeout (float): Maximum wait in seconds.
            
        Returns:
            str: ``prompt``, ``exited``, or ``silent`` for an interactive
                console. A non-interactive channel returns ``send()``'s
                result.
        """
        result = self.channel.input(s,timeout=timeout)
        #result.result()
        return result

    def send_line(self,s,**expections):
        """Send a line of text to the channel.
        
        Args:
            s (str): The line to send.
            
        Returns:
            int: The number of bytes sent.
        """
        return self.channel.send_line(s,**expections)
    ## alias for sendline
    __call__ = send_line
    exec_command = send_line

    def expect(self,rawpat,timeout=None,stdout=True,stderr=True,silent=False):
        """Wait for a pattern to appear in the channel output.
        
        Args:
            rawpat (str): The pattern to match.
            timeout (int, optional): Timeout in seconds. Defaults to None.
            stdout (bool, optional): Whether to check stdout. Defaults to True.
            stderr (bool, optional): Whether to check stderr. Defaults to True.
            silent (bool, optional): Whether to suppress output. Defaults to False.
            
        Returns:
            tuple: A tuple containing (match_index, match_object, matched_text)
        """
        return self.channel.expect(rawpat,timeout,stdout,stderr,silent)

    def wait_for_silent(self,seconds,max_seconds=0):
        """Wait for the channel to become silent for a specified duration.
        
        Args:
            seconds (int): Number of seconds to wait for silence.
            
        Returns:
            bool: True if the channel became silent, False otherwise.
        """
        return self.channel.wait_for_silent(seconds,max_seconds)
    wait = wait_for_silent
    def wait_for_output(self,timeout=0,silent=False):
        """Wait for output from the channel.
        
        Args:
            timeout (int, optional): Timeout in seconds. Defaults to 0.
            silent (bool, optional): Whether to suppress output. Defaults to False.
            
        Returns:
            str: The output received.
        """
        return self.channel.wait_for_output(timeout,silent)

    def send_signal(self,s):
        """Send a signal to the channel.
        
        Args:
            s (str): The signal to send.
            
        Returns:
            bool: True if the signal was sent successfully.
        """
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
        """Switch to another user using su.
        
        Args:
            username (str): The username to switch to.
            password (str, optional): The user's password.
            expect (str, optional): Pattern to expect after su prompt.
            initials (str, optional): Initial characters to send.

            shell: placeholder, just for beening the same as $session.enter()
            get_pty :placeholder, just for beening the same as $session.su()
            
        Returns:
            SuConsole: A console object for su operations.
        """
        ## when localhost is ubuntu, pty is required for su to send password
        return SuConsole(self,username,password,expect=expect,initials=initials,command=command,login=login)
    #sudo(self,password=None,expect=None,initials=None,shell:bool=True,login=True,username=None,get_pty=True):
    def sudo(self,password,username=None,expect=None,initials=None,command=None,login=True,shell=None,get_pty=None):
        """Execute a command with sudo privileges.
        
        Args:
            password (str, optional): The sudo password.
            expect (str, optional): Pattern to expect after sudo prompt.
            initials (str, optional): Initial characters to send.

            shell: placeholder, just for beening the same as $session.enter()
            get_pty: placeholder, just for beening the same as $session.sudo()
            
        Returns:
            SudoConsole: A console object for sudo operations.
        """
        return SudoConsole(self,password,username=username,expect=expect,initials=initials,command=command,login=login)

    def enter(self,command,expect=None,password=None,exit=None,shell=None,get_pty=None,prompt=None):
        """Enter a command and handle its execution.
                   
        Args:
            command (str): The command to execute.
            expect (str, optional): Pattern to expect after command.
            input (str, optional): Input to send after command.
            exit (bool, optional): Whether to exit after command. Defaults to False.
            
            shell: placeholder, just for beening the same as $session.enter()
            get_pty: placeholder, just for beening the same as $session.enter()
            
        Returns:
            EnterConsole: A console object for command execution.
        """

        return EnterConsole(self,command,expect=expect,password=password,exit=exit,prompt=prompt)

    ## $sh      => with _sshscriptstack_[-1].shell(' sh ') 
    ## $sudo    => with _sshscriptstack_[-1].shell(' sudo ') 
    ## $python3 => with _sshscriptstack_[-1].shell(' python3 ')
    def shell(self,*args,**kw):
        """Start a shell session.
        
        Args:
            *args: Command to execute in the shell.
            **kw: Additional keyword arguments for shell configuration.
            
        Returns:
            ShellConsole: A console object for shell operations.
            
        Raises:
            ValueError: If the command is not a valid shell command.
        """
        if len(args) == 0:
            command = ''
        else:
            command = args[0]
            args = args[1:]

        ## ShellConsole with command=False
        assert isinstance(command,str) or isinstance(command,bool)
        if command == False:
            return ShellConsole(self,False,*args,**kw)
        elif command == '':
            return ShellConsole(self,'bash',*args,**kw)
        elif command_is_shell(command):
            ## this command is a kind of shell
            return ShellConsole(self,command,*args,**kw)
        else:
            raise ValueError(f'command "{command}" is not a shell, maybe you want to use $.enter("{command}") instead') 
    def set_prompt(self,prompt):
        self.channel.prompt = prompt
        self.channel._stdout.callback_pattern = prompt
    def log(self, level, msg, *args, **kwargs):
        """Log a message at the specified level.
        
        Args:
            level (int): The logging level.
            msg (str): The message to log.
            *args: Additional arguments for message formatting.
            **kwargs: Keyword arguments forwarded to the logger.
        """
        return self.channel.log(msg, *args, level=level, **kwargs)

    ## wrappers to sshscriptsession(only those seem to be called from a "console". eg.
    ## with $.sudo() as console:
    ##      $.upload() <<-- our wrappers would be called here    
    def upload(self,*args,**kw):
        """Upload files to the remote system.
        
        Args:
            *args: Arguments for the upload operation.
            
        Returns:
            The result of the upload operation.
        """
        return self.channel.owner.session.upload(*args,**kw)

    def download(self,*args,**kw):
        """Download files from the remote system.
        
        Args:
            *args: Arguments for the download operation.
            
        Returns:
            The result of the download operation.
        """
        return self.channel.owner.session.download(*args,**kw)

    def pkey(self,*args,**kw):
        """Get or set the private key for authentication.
        
        Args:
            *args: Arguments for the private key operation.
            
        Returns:
            The result of the private key operation.
        """
        return self.channel.owner.session.pkey(*args,**kw)

    def onedollar(self,command,**kw):
        """Compatibility alias for exec_command()."""
        return self.exec_command(command,**kw)

    def twodollars(self,command,**kw):
        """Compatibility alias for exec_command()."""
        return self.exec_command(command,**kw)

    def __repr__(self):
        """Get a string representation of the wrapper.
        
        Returns:
            str: A string describing the wrapper instance.
        """
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
        threading.current_thread().sshscriptstack.append(self)
        return self
    ## why below??
    #enter = __enter__

    def __exit__(self,*args):
        threading.current_thread().sshscriptstack.pop(self)
        return False
    def exit(self):
        return self.__exit__(None,None,None)

## for SessionWrapper be accessible in channelutils.py (due to recursive importing)
__main__.SessionWrapper = SessionWrapper
