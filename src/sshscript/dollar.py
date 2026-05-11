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
import asyncio
import threading

try:
    from .errorutils import log_debug_8, log_debug, command_is_shell
    from .channelsubprocess import POpenChannel
    from .channelssh import SSHChannel    
except ImportError:
    from errorutils import log_debug_8, log_debug, command_is_shell
    from channelsubprocess import POpenChannel
    from channelssh import SSHChannel    

import pty
from io import BufferedWriter,TextIOWrapper
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

class Dollar(object):
    def __init__(self,session,command=None,for_with=False,**kw):
        """
        Initialize a Dollar object for command execution.
        
        Args:
            session: The session context for command execution.
            command: The command to execute.
            globals: Global variables for command execution.
            locals: Local variables for command execution.
            for_with: Whether this Dollar object is used in a 'with' context.
            kw:
                shell
                get_pty
                input
                env            
        """
        
        command = command.strip() if command else None
        ## this is appeared in "with $command"
        assert not isinstance(for_with,str),f'"for_with" should be bool, not {for_with}'
        self.for_with = for_with

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

        self.call_thread = None
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
    def __del__(self):
        ## ensure to release memory
        if self.call_thread and self.call_thread.is_alive():
            self.call_thread.join()

    def __call__(self,isTwodollars=False,get_pty=None):
        def r():
            nonlocal isTwodollars,get_pty
            newloop = asyncio.new_event_loop()
            asyncio.set_event_loop(newloop)
            self.event_loop = newloop

            if hasattr(asyncio, "get_child_watcher"):
                ## get_child_watcher was depreciated after python v3.12
                # 取得全域 watcher 並綁定到目前的 loop
                watcher = asyncio.get_child_watcher()
                watcher.attach_loop(newloop)

            task = newloop.create_task(self.async_call_worker(isTwodollars,get_pty))
            try:
                newloop.run_forever()
            except Exception as e:
                traceback.print_exc()
            finally:
                tasks = [t for t in asyncio.all_tasks(newloop)]
                if tasks:          
                    for task in tasks:
                        task.cancel()
                    #await asyncio.gather(*tasks, return_exceptions=True)            
                    time.sleep(0.2)
                newloop.run_until_complete(newloop.shutdown_default_executor())
                newloop.run_until_complete(newloop.shutdown_asyncgens())
                if hasattr(asyncio, "get_child_watcher"):
                    ## get_child_watcher was depreciated after python v3.12
                    try:
                        watcher.attach_loop(None)
                    except: pass 
                newloop.close()
                asyncio.set_event_loop(None)
        t = threading.Thread(target=r,daemon=True,name='dollar.call')
        t.start()
        self.call_thread = t
        ## block until self.channel is assigned in __call__worker, which is necessary for "with $command" to work
        while self.channel is None:
            time.sleep(0.01)
        
        if self.for_with:
            return self.channel
        else:
            ## wait for onedollar and twodollar to complete
            while not self.channel.closed:
                time.sleep(0.01)
            return self
    
    async def async_call_worker(self,isTwodollars=False,get_pty=None):
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
            ## necessary for this instance to be put in "with context"
            if self.for_with:
                ## self.channel is SSHChannel  instance
                await self.exec_by_ssh(isTwodollars,get_pty)
                return self.channel
            else:
                await self.exec_by_ssh(isTwodollars,get_pty)
                self.event_loop.stop()
                return self
        else:
            if self.for_with:
                await self.exec_by_subprocess(isTwodollars,get_pty)
                return self.channel
            else:
                ## onedollar or twodollars, wait for the task to complete and return self
                await self.exec_by_subprocess(isTwodollars,get_pty)
                self.event_loop.stop()
                return self

    async def exec_by_subprocess(self,isTwodollars:bool,get_pty:bool):
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
        
        if self.for_with:
            assert '\n' not in self.command
            cpargs = shlex.split(self.command)
            if get_pty:
                log_debug_8(f'with pty for command: {cpargs} in {threading.current_thread()}')
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
                    ## bufsize 0 would be helpful for interactive shell, but
                    ## not good for large and quick outputing process, such as tcpdump
                    bufsize=1024,
                    env=dict(os.environ,TERM='dumb',LANG='en_US.UTF-8',**env),
                )
                
                if cp.poll() is None:
                    ## this command is still running, assign channel and start reading
                    self.channel = POpenChannel(self,cp,[masterFd,slaveFd],masterFd,[masterFd,slaveFd],get_pty) 
                    if not self.sendline2execute: self.channel.hijack(True)
                    #self.channel.start_interaction()
                    asyncio.create_task(self.channel.async_start_interaction())
                else:
                    raise RuntimeError(f'failure on {self.command}(exitcode={cp.poll()})')
            elif 1:
                log_debug_8(f'without pty for command=> {self.command}')
                ## pros:
                ##  su (get_pty=False) works and stderr does not mixed with stdout
                ## cons:
                ##  stderr would having terminal control codes
                #masterFd,slaveFd = pty.openpty()
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
                    asyncio.create_task(self.channel._start_reading())
                    self.channel.close()
                    return ret
                else:
                    #asyncio.get_event_loop().stop()
                    raise RuntimeError(f'failure on {self.command}(exitcode={cp.poll()})')                
            '''
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
                    ret = await self.channel._start_reading()
                    self.channel.close()
                    return ret
                else:
                    raise RuntimeError(f'failure on {self.command}(exitcode={cp.poll()})')                
            '''
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
            self.channel.increase_layer('')
            ## writeback to channel to ensure consitant
            self.channel._exitcode = ret.returncode
            await self.channel._add_stdout_data(ret.stdout)
            await self.channel._add_stderr_data(ret.stderr)
            await self.channel._dump_stdout_err()
            self.channel.close()
            return ret
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
            self.channel.increase_layer('')
            log_debug(f'[subprocess] onedollar:{cpargs}')
            kw.update({'capture_output':True})
            ret = subprocess.run(cpargs,**kw)
            ## writeback to channel to ensure consitant
            self.channel._exitcode = ret.returncode
            await self.channel._add_stdout_data(ret.stdout)
            await self.channel._add_stderr_data(ret.stderr)
            await self.channel._dump_stdout_err()
            self.channel.close()
            return self
        else:
            ## eg. $, $@{}, $f''
            raise ValueError(f'no command to execute')

    async def exec_by_ssh(self,isTwodollars:bool,get_pty:bool)->None:
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

        if self.for_with:
            ## paramiko always not acquire pty to have stdout and stderr seperately
            self.channel = SSHChannel(self,client,get_pty=get_pty)
            asyncio.create_task(self.channel.async_start_interaction())
            #self.channel.start_interaction()
            if not self.sendline2execute:
                self.channel.hijack(True)            
        else:
            ## one-dollar,twodollars           
            if get_pty: kw['get_pty'] = True
            ## The paramiko documentation says:
            ##    "using exec_command or invoke_shell without a pty will ever have data on the stderr stream." So, we always need not a pty.
            ##     paramiko's client

            if 'input' in kw:
                kw_input = kw['input']
                del kw['input']
            else:
                kw_input = None
            
            assert self.command

            if isTwodollars:
                log_debug(f'[{host}]paramiko twodollars:{self.command},{kw}')
                ## for "$$(f'sudo -S ls -l  > {path2download}',input='password')"
                ## this is the best practice
                self.channel = SSHChannel(self,None,get_pty)
                command = f'''bash -c {shlex.quote(self.command)}'''
                self.on_top_of_shell = True ##since we put command into bash to execute

                stdin, stdout,stderr = client.exec_command(command,**kw)
                if kw_input:
                    stdin.write(kw_input+'\n')
                    stdin.flush()
                await self.channel._add_stderr_data(stderr.read())
                await self.channel._add_stdout_data(stdout.read())
                await self.channel._dump_stdout_err()
                self.channel._exitcode = stdout.channel.recv_exit_status()
                log_debug(f'[{host}]exitcode={self.exitcode}')
                ## self.channel.close() will set up self._stdout and self._stderr
                self.channel.close()
                '''
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
                    ## 需要改成asyncio
                    self.channel.close()
                    log_debug(f'[{host}]exitcode={self.exitcode}')
                '''
            else:
                self.channel = SSHChannel(self,None,get_pty)
                log_debug(f'[{host}]paramiko onedollar:{self.command}')
                stdin, stdout,stderr = client.exec_command(self.command,**kw)
                if kw_input:
                    stdin.write(kw_input+'\n')
                    stdin.flush()
                await self.channel._add_stdout_data(stdout.read())
                await self.channel._add_stderr_data(stderr.read())
                await self.channel._dump_stdout_err()
                self.channel._exitcode = stdout.channel.recv_exit_status()
                log_debug(f'[{host}]exitcode={self.exitcode}')
                ## self.channel.close() will set up self._stdout and self._stderr
                self.channel.close()
