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

import os, re, sys, time
import subprocess, shlex, traceback
import __main__
import shutil
import fcntl,termios
try:
    from .errorutils import log_debug_8, log_debug, command_is_shell, command_is_sudo
    from .channelsubprocess import POpenChannel
    from .channelssh import SSHChannel    
except ImportError:
    from errorutils import log_debug_8, log_debug, command_is_shell, command_is_sudo
    from channelsubprocess import POpenChannel
    from channelssh import SSHChannel    

import pty,tty
from io import BytesIO,BufferedWriter,TextIOWrapper
class PTYSlaveWrapper:
    def __init__(self, slave_fd):
        # Create a file object for the slave PTY
        self.slave_file = os.fdopen(slave_fd, 'w', buffering=1)  # Line buffering for TTY
        self.slave_file = TextIOWrapper(self.slave_file.detach(), encoding='utf-8')
    
    def write(self, data):
        # Intercept the write operation
        print(f"Intercepted write: {data!r}",'<' * 100)
        # Forward the data to the slave PTY
        self.slave_file.write(data)
    
    def flush(self):
        # Forward flush to the underlying file
        self.slave_file.flush()
    
    def fileno(self):
        # Return the file descriptor for subprocess compatibility
        return self.slave_file.fileno()
    
    def isatty(self):
        # Ensure the wrapper reports as a TTY
        return self.slave_file.isatty()
    
    def close(self):
        # Close the underlying file
        self.slave_file.close()
    
    __index__ = fileno

class PseudoTTY:
    def __init__(self):
        self.r,self.w = os.pipe()
        # Create a file object for the write end of the pipe
        self.write_file = os.fdopen(self.w, 'bw')
        # Wrap it in a TextIOWrapper to handle text (optional, for text mode)
        self.write_file = BufferedWriter(self.write_file.detach())
    def __getattr__(self,n):
        print('$' * 100,n)
        return getattr(self.write_file,n)
    def fileno(self):
        return self
    def isatty(self):
        print('$' * 100)
        return True
    def write(self,data):
        print('>' * 100)
        self.write_file.write(data)
    def read(self,n):
        return self.r(n)
    def __index__(self):
        return self.write_file.fileno()
     

## ['stdout','stderr','exitcode','channel'] are basic members, exitcode and channel are properties
## v1.1.14: add "exitcode", "channel", v2.0: remove "stdin", because "stdin" is useless
__main__.DollarExportedNames = set(['stdout','stderr','exitcode','channel'])

def export2Dollar(func):    
    """
    Decorator that adds a function's name to the DollarExportedNames set.
    
    Args:
        func: A callable function to be exported.
        
    Returns:
        The original function.
    """
    assert callable(func)
    __main__.DollarExportedNames.add(func.__name__)
    return func

## replace $.stdout, $.stderr to _c.stdout, _c.stderr, $.host     
## v2.0.3 2024/11/24 for compatible with python 3.12
#pstd = re.compile(r'\$\.([a-z]+)')
#def pstdSub(m):
#    """
#    Substitutes $.attribute references with appropriate context variables.
#    
#    Args:
#        m: A regex match object containing the attribute name.
#        
#    Returns:
#        A string with the appropriate context variable reference.
#    """
#    post = m.group(1)
#    if post in __main__.DollarExportedNames:
#        return f'_c.{post}'
#    elif post in __main__.SSHScriptExportedNames:
#        return f'_sshscript_in_context_.{post}'
#    elif post in __main__.SSHScriptExportedNamesByAlias:
#        return f'_sshscript_in_context_.{__main__.SSHScriptExportedNamesByAlias[post]}'
#    elif post == 'break':
#        return f'_sshscript_in_context_._{post}'
#    else:
#        return f'_sshscript_in_context_.{post}'

class Dollar(object):
    def __init__(self,session,command=None,inWith=False,**kw):
        """
        Initialize a Dollar object for command execution.
        
        Args:
            session: The session context for command execution.
            command: The command to execute.
            globals: Global variables for command execution.
            locals: Local variables for command execution.
            inWith: Whether this Dollar object is used in a 'with' context.
        """
        
        command = command.strip() if command else None
        ## this is appeared in "with $command"
        assert not isinstance(inWith,str),f'"inWith" should be bool, not {inWith}'
        self.inWith = inWith

        self.command = command
        self.session = session # Session instance in context
        self.channel = None

        ## channel's sendline is executing a shell command(default)
        self.sendline2execute = True
        #self.shellToRun = None #might be deletable(2026/1/3)
        ## $.enter would use self.on_top_of_shell to know how to get exit code
        self.on_top_of_shell = command_is_shell(self.command)
        ## parameters for run_by_subprocess and run_by_paramiko
        self._parameters_to_execute = kw

    
    @property
    @export2Dollar
    def stdout(self):
        """
        Get the standard output from the command execution.
        
        Returns:
            The standard output as a string.
        """
        return self.channel.stdout

    @property
    @export2Dollar
    def stderr(self):
        """
        Get the standard error from the command execution.
        
        Returns:
            The standard error as a string.
        """
        return self.channel.stderr

    @property
    def exitcode(self):
        """
        Get the exit code from the command execution.
        
        Returns:
            The exit code as an integer.
        """
        return self.channel.exitcode

    def clear(self):
        """
        Clear the channel's buffer if a channel exists.
        """
        if self.channel: self.channel.reset_buffer()

    def __call__(self,isTwodollars=False,get_pty=None):
        """
        Execute the command based on the session context.
        
        Args:
            isTwodollars: Whether this is a two-dollar command execution.
            get_pty: Whether to use a pseudo-terminal.
            
        Returns:
            The channel object if in a 'with' context, otherwise self.
        """
        self.get_pty = get_pty
        if self.session.connected:
            self.exec_by_ssh(isTwodollars,get_pty)

            ## assign self to be the "lastDollar" of owner Session instance
            ## why?
            #assert  self.session._lastDollar is None or self.session._lastDollar == self,f'{self.session._lastDollar} != {self}'
            #self.session._lastDollar = self

            ## necessary for this instance to be put in "with context"
            if self.inWith:
                ## self.channel is SSHChannel  instance
                return self.channel
            else:
                return self
        else:
            self.exec_by_subprocess(isTwodollars,get_pty)
            ## assign self to be the "lastDollar" of owner Session instance
            #self.session._lastDollar = self
            if self.inWith:
                ## self.channel is POpenChannel instance
                return self.channel
            else:
                return self

    def _eval_command(self):
        """
        Evaluate the command to be executed.
        
        Returns:
            A list containing the command to execute, or [None] if no command.
        """
        if self.command:
            return self.command.strip().splitlines(False)
        else:
            return [None]
    

    '''
    def prepare_with_command(self):
        if command_is_sudo(self.command):
            self.shellToRun = 'bash'
        elif command_is_shell(self.command):
            self.shellToRun = self.command
            self.command = ''
            ## channel's sendline is not executing a su or sudo (eg. under "with $su, $sudo)
        else:
            ## v2.0.3 removed arguments for shell, such as '-r --login'
            self.shellToRun = 'bash'
            ## channel's sendline is not executing a shell command
            ## could be inputing something (eg. under "with $python3")
            self.sendline2execute = False
    '''

    def exec_by_subprocess(self,isTwodollars:bool,get_pty:bool):
        """
        Execute a command using subprocess.
        
        Args:
            isTwodollars: Whether this is a two-dollar command execution.
            require_pty: Whether to use a pseudo-terminal.
        """
        kw = self._parameters_to_execute

        if get_pty is None and 'get_pty' in kw:
            get_pty = kw['get_pty']
            self.get_pty = get_pty
            del kw['get_pty']

        assert get_pty is None or isinstance(get_pty,bool)

        if self.inWith:
            assert '\n' not in self.command
            cpargs = shlex.split(self.command)
            if get_pty:
                log_debug_8(f'with pty for command: {self.command}')
                ## master for reading, slave for writing
                masterFd,slaveFd = pty.openpty()
                ## Should use this style of codes, otherwise in CKJ environment something would be wrong
                ## Also, for sudo to prompt "password:", pty is required
                env = kw.get('env',{})
                cp = subprocess.Popen( cpargs,
                    ## when shell=True, it was forced to use /bin/sh
                    shell=False,
                    stdin=slaveFd,
                    stdout=slaveFd,
                    stderr=slaveFd,
                    ## recommanded by python's documentation, disable because it raise errors when enabled
                    ## Note: preexec_fn=os.setsid and start_new_session=True are mutual exclusive
                    start_new_session=True,
                    ##  Run in a new process group to enable bash's job control.
                    #preexec_fn=os.setsid,
                    ## Note: even Text=True, stderr is still bytes
                    text=False,
                    ## more quickly to get results, especially for "tcpdump"
                    bufsize=512,
                    env=dict(os.environ,TERM='dumb',LANG='en_US.UTF-8',**env),
                )
                
                if cp.poll() is None:
                    self.channel = POpenChannel(self,cp,[masterFd],masterFd,[masterFd,slaveFd],get_pty) 
                    if not self.sendline2execute: self.channel.hijack(True)
                    self.channel._start_reading()
                else:
                    raise RuntimeError(f'failure on {self.command}(exitcode={cp.poll()})')
            elif 1:
                log_debug_8(f'without pty for command=> {self.command}')
                ## pros:
                ##  su (get_pty=False) works and stderr does not mixed with stdout
                ## cons:
                ##  stderr would having terminal control codes
                masterFd,slaveFd = pty.openpty()
                cp = subprocess.Popen( cpargs,
                    ## when shell=True, it was forced to use /bin/sh
                    shell=False,
                    #stdin=slaveFd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    #stderr=slaveFd,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    text=False,
                    bufsize=0,
                    env=dict(os.environ,TERM='dumb',LANG='en_US.UTF-8'),
                )
                if cp.poll() is None:
                    self.channel = POpenChannel(self,cp,[cp.stdout.fileno(),cp.stderr.fileno()],cp.stdin.fileno(),[cp.stdin,cp.stderr,cp.stdout],get_pty=get_pty) 
                    if not self.sendline2execute: self.channel.hijack(True)
                    ## necessary for being interactive
                    os.set_blocking(cp.stdout.fileno(), False)
                    self.channel._start_reading()
                else:
                    raise RuntimeError(f'failure on {self.command}(exitcode={cp.poll()})')                
            else:
                log_debug_8(f'without pty for command: {self.command}')
                ## pros:
                ##  su (get_pty=False) works and stderr does not mixed with stdout
                ## cons:
                ##  stderr would having terminal control codes
                masterFd,slaveFd = pty.openpty()
                cp = subprocess.Popen( cpargs,
                    ## when shell=True, it was forced to use /bin/sh
                    shell=False,
                    stdin=slaveFd,
                    stdout=subprocess.PIPE,
                    stderr=slaveFd,
                    start_new_session=True,
                    text=False,
                    bufsize=0,
                    env=dict(os.environ,TERM='dumb',LANG='en_US.UTF-8'),
                )
                if cp.poll() is None:
                    self.channel = POpenChannel(self,cp,[cp.stdout.fileno(),masterFd],masterFd,[masterFd,slaveFd,cp.stdout],get_pty=get_pty) 
                    if not self.sendline2execute: self.channel.hijack(True)
                    ## necessary for being interactive
                    os.set_blocking(cp.stdout.fileno(), False)
                    self.channel._start_reading()
                else:
                    raise RuntimeError(f'failure on {self.command}(exitcode={cp.poll()})')                
        elif isTwodollars:
            if 'input' in kw:
                kw['input'] = kw['input'].encode('utf8')
            kw['shell'] = True
            self.on_top_of_shell = True ## since we force to use shell
            ## where shell=False, subprocess.run 
            cpargs = self.command
            kw['text'] = False
            env = dict(os.environ,TERM='dumb',LANG='en_US.UTF-8',**kw.get('env',{}))
            kw['env'] = env
            log_debug(f'[subprocess] twodollar:{cpargs}')
            kw.update({'capture_output':True})
            ret = subprocess.run(cpargs,**kw)
            ## with_pty is always False
            self.channel = POpenChannel(self,None,None,None,[],False)
            ## writeback to channel to ensure consitant
            self.channel._exitcode = ret.returncode
            self.channel._add_stdout_data(ret.stdout)
            self.channel._add_stderr_data(ret.stderr)
            self.channel._dump_stdout_err()
            self.channel.close()
        elif self.command:
            ## onedollar 
            if 'input' in kw:
                kw['input'] = kw['input'].encode('utf8')
            if not 'shell' in kw: kw['shell'] = False
            ## where shell=False, subprocess.run 
            if kw['shell']:
                cpargs = self.command
                self.on_top_of_shell = True ## since been forced to use shell
            else:
                cpargs = shlex.split(self.command)
            kw['text'] = False
            ## with_pty is always False
            self.channel = POpenChannel(self,None,None,None,[],False)
            log_debug(f'[subprocess] onedollar:{cpargs}')
            kw.update({'capture_output':True})
            ret = subprocess.run(cpargs,**kw)
            ## writeback to channel to ensure consitant
            self.channel._exitcode = ret.returncode
            self.channel._add_stdout_data(ret.stdout)
            self.channel._add_stderr_data(ret.stderr)
            self.channel._dump_stdout_err()
            self.channel.close()
        else:
            ## eg. $, $@{}, $f''
            raise ValueError(f'no command to execute')

    def exec_by_ssh(self,isTwodollars:bool,get_pty:bool)->None:
        """
        Executes a command over SSH.

        Args:
            isTwodollars: Whether the command is a two-dollar command.
            require_pty: Whether to use a pseudo-terminal.

        """        
        host = self.session.host;
        client = self.session._client       
        kw = self._parameters_to_execute

        ## with_pty of ssh default to False for having stderr output
        if get_pty is None: get_pty = kw.get('get_pty',False)
        ## allow use "env" (same as subprocess.run) instead of "environment"
        if 'env' in kw:
            kw['environment'] = kw['env']
            del kw['env']

        if self.inWith:
            ## paramiko always not acquire pty to have stdout and stderr seperately
            self.channel = SSHChannel(self,client,get_pty=get_pty)
            if not self.sendline2execute:
                self.channel.hijack(True)            
        else:
            ## one-dollar,twodollars           
            if get_pty: kw['get_pty'] = True
            ## The paramiko documentation says:
            ## "using exec_command or invoke_shell without a pty will ever have data on the stderr stream." So, we always need not a pty.
            ## paramiko's client

            if 'input' in kw:
                kw_input = kw['input']
                del kw['input']
            else:
                kw_input = None
            
            assert self.command

            if isTwodollars:
                log_debug(f'[{host}]paramiko twodollars:{self.command},{kw}')
                if 1:
                    ## for "$$(f'sudo -S ls -l  > {path2download}',input='password')"
                    ## this is the best practice
                    self.channel = SSHChannel(self,None,get_pty)
                    
                    command = f'''bash -c {shlex.quote(self.command)}'''
                    self.on_top_of_shell = True ##since we put command into bash to execute

                    stdin, stdout,stderr = client.exec_command(command,**kw)
                    if kw_input:
                        stdin.write(kw_input+'\n')
                        stdin.flush()
                    self.channel._add_stderr_data(stderr.read())
                    self.channel._add_stdout_data(stdout.read())
                    self.channel._dump_stdout_err()
                    self.channel._exitcode = stdout.channel.recv_exit_status()
                    log_debug(f'[{host}]exitcode={self.exitcode}')
                    ## self.channel.close() will set up self._stdout and self._stderr
                    self.channel.close()                    
                elif kw_input:
                    ## borrowed from paramiko source (client.invoke_shell)
                    channel = client._transport.open_session()
                    if get_pty:
                        channel.get_pty('dumb')
                    ## update_environment() must prior to invoke_shell()
                    if kw.get('environment'):
                        channel.update_environment(kw['environment'])
                    
                    channel.invoke_shell()
                    self.on_top_of_shell = True ## since "invoke_shell()" is called

                    command = self.command
                    ## set self.command to None would make SSHChannel not to execute it,
                    ## then requesting its exitcode. Because we would "input" it later.
                    self.command = None
                    self.channel = SSHChannel(self,channel,get_pty=True)
                    self.channel.input(command)
                    self.channel.wait_for_silent(1)
                    self.channel.input(kw_input)
                    _ = self.channel.exitcode
                    ## self.channel.close() will set up self._stdout and self._stderr
                    self.channel.close()
                    log_debug(f'[{host}]exitcode={self.exitcode}')
            else:
                self.channel = SSHChannel(self,None,get_pty)
                log_debug(f'[{host}]paramiko onedollar:{self.command}')
                stdin, stdout,stderr = client.exec_command(self.command,**kw)
                if kw_input:
                    stdin.write(kw_input+'\n')
                    stdin.flush()
                self.channel._add_stdout_data(stdout.read())
                self.channel._add_stderr_data(stderr.read())
                self.channel._dump_stdout_err()
                self.channel._exitcode = stdout.channel.recv_exit_status()
                log_debug(f'[{host}]exitcode={self.exitcode}')
                ## self.channel.close() will set up self._stdout and self._stderr
                self.channel.close()
