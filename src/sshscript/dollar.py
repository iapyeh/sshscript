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
import subprocess, shlex
import __main__
import asyncio
import threading

if __package__:
    from .errorutils import command_requires_shell, command_summary, get_logger
    from .channelsubprocess import POpenChannel
    from .channelssh import SSHChannel    
else:
    from errorutils import command_requires_shell, command_summary, get_logger
    from channelsubprocess import POpenChannel
    from channelssh import SSHChannel    
logger = get_logger()
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
    def __init__(self,session,command=None,for_with=False,use_shell=None,
                 shell_executable=None,**kw):
        """
        Initialize a Dollar object for command execution.
        
        Args:
            session: The session context for command execution.
            command: The command to execute.
            globals: Global variables for command execution.
            locals: Local variables for command execution.
            for_with: Whether this Dollar object is used in a 'with' context.
            use_shell: None for automatic detection, otherwise a boolean.
            shell_executable: Shell used for shell mode; defaults to /bin/sh.
            kw:
                get_pty
                input
                env            
        """
        
        if not for_with and not isinstance(command,str):
            raise TypeError(f'command must be str, not {type(command).__name__}')
        command = command.strip() if isinstance(command,str) else command
        ## this is appeared in "with $command"
        assert not isinstance(for_with,str),f'"for_with" should be bool, not {for_with}'
        self.for_with = for_with

        self.command = command
        self.session = session # Session instance in context
        self.channel = None
        self.use_shell = use_shell
        self.shell_executable = shell_executable
        self.shell_reasons = []

        if not for_with:
            if use_shell is None and command:
                self.use_shell,self.shell_reasons = command_requires_shell(command)
            elif use_shell is not None:
                self.use_shell = bool(use_shell)

        ## channel's sendline is executing a shell command(default)
        self.sendline2execute = True
        #self.shellToRun = None #might be deletable(2026/1/3)
        ## $.enter would use self.on_top_of_shell to know how to get exit code
        #self.on_top_of_shell = command_is_shell(self.command)
        ## parameters for run_by_subprocess and run_by_paramiko
        self._parameters_to_execute = kw

        self.call_thread = None
        self._worker_exception = None
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
    #def __del__(self):
    #    ## ensure to release memory
    #    if self.call_thread and self.call_thread.is_alive():
    #        self.call_thread.join()
    def __del__(self):
        thread = self.call_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def __call__(self,get_pty=None):
        def r():
            nonlocal get_pty
            newloop = asyncio.new_event_loop()
            asyncio.set_event_loop(newloop)
            self.event_loop = newloop

            if hasattr(asyncio, "get_child_watcher"):
                ## get_child_watcher was depreciated after python v3.12
                # 取得全域 watcher 並綁定到目前的 loop
                watcher = asyncio.get_child_watcher()
                watcher.attach_loop(newloop)
            
            def cleanup():
                tasks = [t for t in asyncio.all_tasks(newloop)]
                if tasks:          
                    for task in tasks:
                        task.cancel()
                    newloop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                    #time.sleep(0.2)
                if hasattr(asyncio, "get_child_watcher"):
                    ## get_child_watcher was depreciated after python v3.12
                    try:
                        watcher.attach_loop(None)
                    except Exception:
                        pass
                #newloop.stop()
                if newloop.is_running() or not newloop.is_closed():
                    newloop.run_until_complete(newloop.shutdown_default_executor())
                    newloop.run_until_complete(newloop.shutdown_asyncgens())
                newloop.close()
                asyncio.set_event_loop(None)
            '''
            def task_exception_handler(t):
                try:
                    t.result()
                except asyncio.CancelledError:
                    newloop.stop()
                except Exception as exc:
                    self._worker_exception = exc
                    logger.debug(
                        'Command worker failed (exception_type=%s)',
                        type(exc).__name__,
                    )
                    ## end of the run_forever
                    newloop.stop()
            '''
            def task_exception_handler(task):
                try:
                    task.result()
                except asyncio.CancelledError:
                    if self.channel is not None and not self.channel.closed:
                        self.channel.fail(
                            EOFError('command worker was cancelled')
                        )

                except BaseException as exc:
                    self._worker_exception = exc

                    if self.channel is not None:
                        self.channel.fail(exc)

                    logger.debug(
                        'Command worker failed (exception_type=%s)',
                        type(exc).__name__,
                    )
                finally:
                    newloop.stop()            
            try:
                task= newloop.create_task(self.async_call_worker(get_pty))
                task.add_done_callback(task_exception_handler)
                newloop.run_forever()
            finally:
                cleanup()

        t = threading.Thread(target=r,daemon=True,name='dollar.call')
        t.start()
        ## block until self.channel is assigned in __call__worker, which is necessary for "with $command" to work
        ## When exception happend in thread at initial stage, t.is_alive() is False
        while t.is_alive() and self.channel is None:
            time.sleep(0.01)
        
        #print('#'*100,self.channel,t.is_alive())
        self.call_thread = t
        if self._worker_exception is not None:
            raise self._worker_exception
        if self.channel is None:
            raise RuntimeError(
                'Command worker exited before channel initialization'
            )

        if self.for_with:
            return self.channel
        else:
            ## wait for onedollar and twodollar to complete
            while (
                not self.channel.closed
                and self._worker_exception is None
                and t.is_alive()
            ):
                time.sleep(0.01)
            if self._worker_exception is not None:
                raise self._worker_exception
            if not self.channel.closed:
                raise RuntimeError(
                    'Command worker exited before closing the channel'
                )
            return self

    async def async_call_worker(self,get_pty=None):
        """
        Execute the command based on the session context.
        
        Args:
            get_pty: Whether to use a pseudo-terminal.
            
        Returns:
            The channel object if in a 'with' context, otherwise self.
        """
        self.get_pty = get_pty
        if self.session.connected:
            ## necessary for this instance to be put in "with context"
            if self.for_with:
                ## self.channel is SSHChannel  instance
                await self.exec_by_ssh(get_pty)
                return self.channel
            else:
                await self.exec_by_ssh(get_pty)
                self.event_loop.stop()
                return self
        else:
            if self.for_with:
                await self.exec_by_subprocess(get_pty)
                return self.channel
            else:
                ## A one-shot command waits for completion and returns self.
                await self.exec_by_subprocess(get_pty)
                self.event_loop.stop()
                return self
    async def exec_by_subprocess(self,get_pty:bool):
        """
        Execute a command using subprocess.
        
        Args:
            require_pty: Whether to use a pseudo-terminal.
        """
        assert get_pty is None or isinstance(get_pty,bool)
        kw = self._parameters_to_execute
        if get_pty is None and 'get_pty' in kw:
            get_pty = kw['get_pty']
            self.get_pty = get_pty
            del kw['get_pty']
        ## default env
        allowed_keys = {
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "VIRTUAL_ENV",
            "CONDA_PREFIX",
            "CONDA_DEFAULT_ENV",
            "PYTHONPATH",
        }
        env = {k: v for k, v in os.environ.items() if k in allowed_keys}
        env.update({
            'TERM':'dumb','LANG':'en_US.UTF-8',
            'PATH':os.environ.get('PATH','')
        })
        env.update(kw.get('env',{}))

        if self.for_with:
            assert '\n' not in self.command
            cpargs = shlex.split(self.command)
            summary = command_summary(cpargs)
            if get_pty:
                logger.debug(
                    'Starting interactive subprocess '
                    '(executable=%s, pty=%s, argc=%d)',
                    summary['executable'],
                    True,
                    summary['arg_count'],
                )
                ## master for reading, slave for writing
                masterFd,slaveFd = pty.openpty()
                ## Should use this style of codes, otherwise in CKJ environment something would be wrong
                ## Also, for sudo to prompt "password:", pty is required
                try:
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
                        env=env,
                    )
                except BaseException:
                    # Popen 失敗時，沒有人會接管 master。
                    try:
                        os.close(masterFd)
                    except OSError:
                        pass
                    raise   
                finally:
                    # Child 已經取得 slave；parent 絕對不能繼續保留或讀取它。
                    try:
                        os.close(slaveFd)
                    except OSError:
                        pass           
                                      
                #if cp.poll() is None:
                #    ## this command is still running, assign channel and start reading
                #    self.channel = POpenChannel(self,cp,[masterFd,slaveFd],masterFd,[masterFd,slaveFd],get_pty) 
                #    if not self.sendline2execute: self.channel.hijack(True)
                #    asyncio.create_task(self.channel.async_start_interaction())
                #else:
                #    raise RuntimeError(
                #        'Subprocess exited before channel initialization '
                #        f'(exit_code={cp.poll()})'
                #    )
                if cp.poll() is not None:
                    returncode = cp.wait()

                    try:
                        os.close(masterFd)
                    except OSError:
                        pass

                    raise RuntimeError(
                        'Subprocess exited before channel initialization '
                        f'(exit_code={returncode})'
                    )

                # PTY 只有一個可讀取的 merged-output stream。
                # stdin 與 stdout 都使用 masterFd。
                self.channel = POpenChannel(
                    self,
                    cp,
                    [masterFd],
                    masterFd,
                    [masterFd],
                    get_pty=True,
                )
                
                if not self.sendline2execute:
                    self.channel.hijack(True)

                #asyncio.create_task(self.channel.async_start_interaction())                
                await self.channel.async_start_interaction()

            elif 1:
                logger.debug(
                    'Starting interactive subprocess '
                    '(executable=%s, pty=%s, argc=%d)',
                    summary['executable'],
                    False,
                    summary['arg_count'],
                )
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
                    env=env,
                )
                if cp.poll() is None:
                    self.channel = POpenChannel(self,cp,[cp.stdout.fileno(),cp.stderr.fileno()],cp.stdin.fileno(),[cp.stdin,cp.stderr,cp.stdout],get_pty=get_pty) 
                    if not self.sendline2execute: self.channel.hijack(True)
                    
                    ## necessary for being interactive
                    os.set_blocking(cp.stdout.fileno(), False)
                    
                    #asyncio.create_task(self.channel.async_start_interaction())
                    await self.channel.async_start_interaction()

                else:
                    raise RuntimeError(
                        'Subprocess exited before channel initialization '
                        f'(exit_code={cp.poll()})'
                    )
            '''
            else:
                logger.debug('Starting interactive subprocess without a PTY')
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
        elif self.command:
            if 'input' in kw and isinstance(kw['input'],str):
                kw['input'] = kw['input'].encode('utf8')
            if 'env' in kw:
                kw['env'] = dict(
                    os.environ,
                    TERM='dumb',
                    LANG='en_US.UTF-8',
                    **kw['env'],
                )
            if self.use_shell:
                shell_executable = self.shell_executable or '/bin/sh'
                cpargs = [shell_executable,'-c',self.command]
            else:
                cpargs = shlex.split(self.command)
            summary = command_summary(cpargs)
            kw['text'] = False
            ## with_pty is always False
            self.channel = POpenChannel(self,None,None,None,[],False)
            self.channel.increase_layer('')
            logger.debug(
                'Executing subprocess '
                '(executable=%s, shell=%s, pty=%s, argc=%d, '
                'shell_reasons=%s, command_length=%d)',
                summary['executable'],
                self.use_shell,
                False,
                summary['arg_count'],
                self.shell_reasons,
                len(self.command),
            )
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

    async def exec_by_ssh(self,get_pty:bool)->None:
        """
        Executes a command over SSH.

        Args:
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

            if not self.sendline2execute:
                self.channel.hijack(True)            

            #asyncio.create_task(self.channel.async_start_interaction())
            await self.channel.async_start_interaction()

        else:
            ## One-shot direct or shell command.
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

            if self.use_shell:
                shell_executable = self.shell_executable or '/bin/sh'
                command = f'{shlex.quote(shell_executable)} -c {shlex.quote(self.command)}'
                summary = command_summary([shell_executable])
                argc = None
            else:
                argv = shlex.split(self.command)
                command = 'exec ' + ' '.join(shlex.quote(str(arg)) for arg in argv)
                summary = command_summary(argv)
                argc = summary['arg_count']

            logger.debug(
                'Executing SSH command '
                '(host=%s, executable=%s, shell=%s, pty=%s, argc=%s, '
                'shell_reasons=%s, command_length=%d)',
                host,
                summary['executable'],
                self.use_shell,
                get_pty,
                argc,
                self.shell_reasons,
                len(self.command),
            )
            self.channel = SSHChannel(self,None,get_pty)
            stdin, stdout,stderr = client.exec_command(command,**kw)
            if kw_input:
                stdin.write(kw_input+'\n')
                stdin.flush()
            await self.channel._add_stdout_data(stdout.read())
            await self.channel._add_stderr_data(stderr.read())
            await self.channel._dump_stdout_err()
            self.channel._exitcode = stdout.channel.recv_exit_status()
            logger.debug(
                'SSH command completed (host=%s, exit_code=%s)',
                host,
                self.exitcode,
            )
            self.channel.close()
