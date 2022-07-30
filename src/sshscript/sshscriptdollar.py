# Copyright (C) 2022-2026  Hsin Yuan Yeh <iapyeh@gmail.com>
#
# This file is part of Sshscript.
#
# Sshscript is free software; you can redistribute it and/or modify it under the
# terms of the MIT License.
#
# Sshscript is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the MIT License for more details.
#
# You should have received a copy of the MIT License along with Sshscript;
# if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA.

from glob import glob
import os, re
import subprocess, shlex
import __main__
import shutil, asyncio
try:
    from sshscripterror import SSHScriptError
    from sshscriptchannel import POpenChannel, ParamikoChannel#,POpenPipeChannel
except ImportError:
    from .sshscripterror import SSHScriptError
    from .sshscriptchannel import POpenChannel, ParamikoChannel#,POpenPipeChannel
try:
    import pty
except ImportError:
    # pty is not available on Windows
    pty = None

pvarS = re.compile('(\b?)\@\{(.+?)\}',re.S)

global logger, loop
logger = None
loop = asyncio.get_event_loop()

class SSHScriptDollar(object):
    exportedProperties = set(['stdout','stderr','stdin'])
    # aka $shell-commmand , or coverted "_c"
    def __init__(self,ssId,cmd=None,globals=None,locals=None,inWith=False):
        global logger
        # assign logger to sshscript's logger
        if logger is None: logger = __main__.SSHScript.logger
        self.args = (ssId,cmd,globals,locals)
        self.sshscript = None #執行的脈絡下的 sshscript instance
        self.inWith = inWith
        #self.hasExit = False # True if user calls exit()
        self.invokeShell = False
        self.wrapper = None
        self.bufferedOutputData = b''
        self.bufferedErrorData = b''
        # set os.environ['NO_PTY']='1' to disable pty
        self.usePty = pty and os.environ.get('NO_PTY','') != '1'
    
    def __call__(self,invokeShell=False,deepCall=True):
        ssId = self.args[0]
        self.sshscript = __main__.SSHScript.items[ssId] if ssId else __main__.SSHScript.inContext
        # reset self.sshscript's stdout and stderr
        if self.sshscript.host:
            self.execBySSH(invokeShell,deepCall)
            # necessary for this instance to be put in "with context"
            if self.inWith:
                # self.channel is ParamikoChannel  instance
                return self.channel
            else:
                return self
        else:
            self.execBySubprocess(invokeShell)
            if self.inWith:
                # self.channel is POpenChannel instance
                return self.channel
            else:
                return self
    
    def evalCommand(self):
        # common utility for execBySSH and  execBySubprocess
        (ssId,cmd,_globals,_locals) = self.args
        # eval @{py-var} in $shell-command
        def pvarRepl(m):
            logger.debug(f'calling eval({m.group(2)}) in "${cmd}"')
            return f'{eval(m.group(2),_globals,_locals)}'
        cmd = pvarS.sub(pvarRepl,cmd)
        # should be one-line command
        cmds = [x.strip() for x in cmd.split('\n')]
        cmds = [x for x in cmds if (x and not x.startswith('#'))]
        return cmds

    def execBySubprocess(self,invokeShell):
        global loop
        #(ssId,cmd,_globals,_locals) = self.args
        cmds = self.evalCommand()
        # should be one-line command
        #cmds = [x.strip() for x in cmd.split('\n')]
        #cmds = [x for x in cmds if (x and not x.startswith('#'))]
        #hasMultipleLines = len(cmds) > 1

        # 只要有with,一定是invokeShell(with ${} same as with $${})
        if self.inWith: invokeShell = True

        # implement stdin, and timeout (default to 60)
        timeout = float(os.environ.get('CMD_TIMEOUT',60))
        
        if invokeShell:
            self.invokeShell = True
            # prepare shell command
            shCmd = os.environ.get('SHELL')
            if shCmd is None:
                shCmd = shutil.which('bash')
                if shCmd is None:
                    raise RuntimeError('no shell command found')

            # arguments for shell, such as '-r --login'
            shArgs = os.environ.get('SHELL_ARGUMENTS')
            if shArgs is not None:
                shCmd += ' ' + shArgs

            # prepare popen command
            args = shlex.split(shCmd)
            logger.debug(f'subprocess.Popen {args}')
            if self.usePty:
                # ref: https://errorsfixing.com/run-interactive-bash-in-dumb-terminal-using-python-subprocess-popen-and-pty/
                # ref: https://stackoverflow.com/questions/19880190/interactive-input-output-using-python
                masterFd,slaveFd = zip(pty.openpty(),pty.openpty())                
                #masterFd,slaveFd = zip([subprocess.PIPE,subprocess.PIPE],[subprocess.PIPE,subprocess.PIPE])       
                #masterFd,slaveFd = zip(os.pipe(),os.pipe())
                cp = subprocess.Popen(args,
                    # 會引起  RuntimeWarning: line buffering (buffering=1) isn't supported in binary mode,
                    #bufsize=1,
                    # 會導致  cannot set terminal process group (-1)
                    #stdin=slaveFd[0],stdout=slaveFd[0],stderr=slaveFd[1],
                    stdin=subprocess.PIPE,stdout=slaveFd[0],stderr=slaveFd[1],
                    # Run in a new process group to enable bash's job control.
                    preexec_fn=os.setsid,
                    # Run in "dumb" terminal.
                    env=dict(os.environ, TERM='vt100'),
                    )
                self.channel = POpenChannel(self,cp,timeout,masterFd,slaveFd)                    
            else:
                #windows
                masterFd,slaveFd = zip(os.pipe(),os.pipe())
                cp = subprocess.Popen(args,
                    # 會引起  RuntimeWarning: line buffering (buffering=1) isn't supported in binary mode,
                    #bufsize=1,
                    #stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,stdout=slaveFd[0],stderr=slaveFd[1],
                    # Run in a new process group to enable bash's job control.
                    preexec_fn=os.setsid,
                    # Run in "dumb" terminal.
                    env=dict(os.environ, TERM='vt100'),
                    )                
                self.channel = POpenChannel(self,cp,timeout,masterFd,slaveFd)

            # value is None. for what? 
            self.stdin = cp.stdin

            # wait for bash to start up
            try:
                # 等到初始IO結束後0.5second才繼續
                self.channel.wait(0.5)
            except TimeoutError:
                pass
            
            for command in cmds:
                self.channel.sendline(command)
                #loop.run_until_complete(self.channel.waitio())
                self.channel.wait()
            
            if not self.inWith:
                self.channel.close()

        else:
            
            '''
            # not invoke shell
            if self.usePty:
                self.channel = POpenChannel(self,None,timeout)
            else:
                self.channel = POpenPipeChannel(self,None,timeout)
            '''
            self.channel = POpenChannel(self,None,timeout)

            for command in cmds:
                # it is recommended to pass args as a sequence.... If shell is True, 
                # it is recommended to pass args as a string rather than as a sequence.
                args = shlex.split(command)
                if  ('|' in args) : raise SSHScriptError('| works only in shell mode, consider to run with $$',501)
                if  ('>' in args) : raise SSHScriptError('> not works in $',502)
                logger.debug(f'subprocess.Popen {args}')
                cp = subprocess.Popen(args,
                    # 會引起  RuntimeWarning: line buffering (buffering=1) isn't supported in binary mode,
                    #bufsize=1,
                    env=os.environ.copy(),
                    stdin=subprocess.PIPE,stderr=subprocess.PIPE,stdout=subprocess.PIPE,
                    shell=invokeShell)

                # outs,errs are bytes
                try:
                    outs, errs = cp.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    cp.kill()
                    outs, errs = cp.communicate()
                self.stdin = cp.stdin
                #多行時，$.stdout, $.stderr是所有的總和
                self.channel.addStdoutData(outs)
                self.channel.addStderrData(errs)

            # self.channel.close() will not call  self.channel.recv()
            # so we need to call it here
            self.channel.recv()
            self.channel.close()
            if self.channel.stderr and self.sshscript._paranoid:
                raise SSHScriptError(self.channel.stderr)
    
    def execBySSH(self,invokeShell,deepCall):
        global loop

        cmds = self.evalCommand()
        #cmds = [x.strip() for x in cmd.split('\n')]
        #cmds = [x for x in cmds if (x and not x.startswith('#'))]

        # provide value of $.username, $.port, $.host
        self.host = self.sshscript.host;
        self.username = self.sshscript.username;
        self.port = self.sshscript.port
        
        # 只要有with,一定是invokeShell(with ${} same as with $${})
        if self.inWith: invokeShell = True

        # implement stdin, and timeout (default to 60)
        timeout = float(os.environ.get('CMD_TIMEOUT',60))             

        client = self.sshscript.client if deepCall else self.sshscript._client
        
        if invokeShell:
            self.invokeShell = True
            # REF: https://stackoverflow.com/questions/6203653/how-do-you-execute-multiple-commands-in-a-single-session-in-paramiko-python/6203877#6203877
            
            self.channel = ParamikoChannel(self,client, timeout)
            
            for command in cmds:
                self.channel.sendline(command)# write to queue
                self.channel.wait()
            
            self.channel.wait(1)
            #loop.run_until_complete(self.channel.waitio(1))
            if not self.inWith:
                self.channel.close()

        else:
            self.channel = ParamikoChannel(self,None, timeout)
            for command in cmds:
                logger.debug(f'execute: {command}')
                # The paramiko documentation says:
                # "using exec_command or invoke_shell without a pty will ever have data on the stderr stream."
                # So, we always need not a pty.
                stdin, stdout,stderr = client.exec_command(command,get_pty=0,timeout=timeout)
                self.stdin = stdin
                self.channel.addStdoutData(stdout.read())
                self.channel.addStderrData(stderr.read())

            # self.channel.close() will not call self.channel.recv()
            # so, we need to call it here
            self.channel.recv()
            self.channel.close()
            if self.channel.stderr and self.sshscript._paranoid:
                raise SSHScriptError(self.channel.stderr)
        
    def __iter__(self):
        """
        Support for the iterator protocol.
        with $ as fd: # fd is an instance of SSHScriptDollar
            for line in fd:
                print(line)
        """
        while True:
            line = self.wait('\n')
            if not line: break
            yield line
    # protocol of "with  as "
    def __enter__(self):
        return self
    # protocol of "with  as "
    def __exit__(self,*args):
        if self.invokeShell:
            if self.sshscript.host: # execute by ssh
                self.channel.close()
            else: 
                self.stdin.close()

        if not hasattr(self,'stdout') or not isinstance(self.stdout,str):
            self.getResult()
                
