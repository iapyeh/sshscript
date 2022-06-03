#!/usr/bin/env python3
import os, sys, traceback, time, re, random, glob
import queue, threading
import subprocess, shlex, socket
import pty, shutil, asyncio
try:
    from sshscripterror import SSHScriptError
    from sshscriptchannel import POpenChannel, ParamikoChannel
except ImportError:
    from .sshscripterror import SSHScriptError
    from .sshscriptchannel import POpenChannel, ParamikoChannel
# replace @{var} in $shell-command
#pvar = re.compile('(\b?)\@\{(.+)\}')
# replace $.stdout, $.stderr to _c.stdout, _c.stderr, $.host in $LINE
#pstd = re.compile('(\b?)\$(\.[a-z]+)\b?')
# replace @{var} in py scripts
pvarS = re.compile('(\b?)\@\{(.+?)\}',re.S)

import __main__


global logger
logger = None
loop = asyncio.get_event_loop()

class SSHScriptDollar(object):
    exportedProperties = set(['stdout','stderr','stdin'])
    # aka $shell-commmand , or coverted "_c"
    def __init__(self,ssId,cmd=None,globals=None,locals=None,inWith=False):
        global logger
        # assign logger 
        if logger is None: logger = __main__.logger

        # ss = instance of SSHScript
        self.args = (ssId,cmd,globals,locals)
        self.sshscript = None #執行的脈絡下的 sshscript instance
        self.inWith = inWith
        self.hasExit = False # True if user calls exit()
        self.invokeShell = False
        self.wrapper = None
        #self.writingQueue = queue.SimpleQueue()
        #self.thread = None
        self.bufferedOutputData = b''
        self.bufferedErrorData = b''
        #self.cachedStdin = stdin
    """
    def setResult(self,ctx,channel=None):
        stdin, stdout,stderr = ctx
        self.stdin = stdin
        self.stdoutStream = stdout
        self.stderrStream = stderr
        self.channel = channel
    
    def getResult(self):
        #if self.sshscript.host and self.invokeShell:
        #    while self.channel.active and not self.channel.recv_ready():  time.sleep(0.1)
        #    assert self.channel.active
        
        self.stdin.flush()
        self.stdin.close()
        try:
            stdout = self.stdoutStream.read()
        except socket.timeout:
            stdout = b''
        
        self.stdout = (self.bufferedOutputData + stdout).decode('utf8')
        
        try:
            stderr = self.stderrStream.read()
        except socket.timeout:
            stderr = b''
        
        self.stderr = (self.bufferedErrorData + stderr).decode('utf8')
                
        # "close channel" should be at the end
        if self.channel: self.channel.close()

        if self.stderr.strip() and self.sshscript._paranoid:
            raise SSHScriptError(self.stderr)
        
    """
    def __call__(self,invokeShell=False,deepCall=True):
        #(ssId,cmd,_globals,_locals) = self.args
        #SSHScript = _globals['SSHScript']
        ssId = self.args[0]
        self.sshscript = __main__.SSHScript.items[ssId] if ssId else __main__.SSHScript.inContext
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
        return cmd

    def execBySubprocess(self,invokeShell):
        (ssId,cmd,_globals,_locals) = self.args
        cmd = self.evalCommand()
        # should be one-line command
        cmds = [x.strip() for x in cmd.split('\n')]
        cmds = [x for x in cmds if (x and not x.startswith('#'))]
        hasMultipleLines = len(cmds) > 1

        # prepare pre-assigned stdin
        """
        if self.cachedStdin:
            if hasattr(self.cachedStdin,'read'):
                input = self.cachedStdin.read()
            else:
                input = self.cachedStdin
        else:
            input = b''
        """

        # 只要有with,一定是invokeShell(with ${} same as with $${})
        if self.inWith: invokeShell = True

        # implement stdin, and timeout (default to 60)
        timeout = self.sshscript._timeout or 60    
        
        if invokeShell:
            self.invokeShell = True
            # prepare shell command
            shCmd = os.environ.get('SHELL')
            if shCmd is None:
                shCmd = shutil.which('bash')
                if shCmd is None:
                    raise RuntimeError('no shell command found')
            logger.debug(f'shell: {shCmd}')
            if self.inWith or hasMultipleLines:
                # prepare popen command
                args = shlex.split(shCmd)

                # ref: https://errorsfixing.com/run-interactive-bash-in-dumb-terminal-using-python-subprocess-popen-and-pty/
                # ref: https://stackoverflow.com/questions/19880190/interactive-input-output-using-python
                masterFd,slaveFd = zip(pty.openpty(),pty.openpty())                
                cp = subprocess.Popen(args,
                    # 會引起  RuntimeWarning: line buffering (buffering=1) isn't supported in binary mode,
                    #bufsize=1,
                    stdin=slaveFd[0],stdout=slaveFd[0],stderr=slaveFd[1],
                    # Run in a new process group to enable bash's job control.
                    preexec_fn=os.setsid,
                    # Run in "dumb" terminal.
                    env=dict(os.environ, TERM='vt100'),
                    )

                # value is None. for what? 
                self.stdin = cp.stdin
                
                self.channel = POpenChannel(self,cp,timeout,masterFd,slaveFd)

                # wait for bash to start up
                try:
                    # 等到初始IO結束後0.5second才繼續
                    self.channel.wait(0.5)
                except TimeoutError:
                    pass
                for cmd in cmds:
                    #print('send>>',cmd)
                    self.channel.sendline(cmd)#(masterFd,(cmd+'\n').encode('utf8'))
                    loop.run_until_complete(self.channel.waitio())
                if not self.inWith:
                    self.channel.close()

            else:
                # inVokeShell, but only single line and not in with
                # prepare popen command
                self.channel = POpenChannel(self,None,timeout)
                #shCmd = cmds.pop(0)
                args = shlex.split(shCmd)
                cp = subprocess.Popen(args,
                    # 會引起  RuntimeWarning: line buffering (buffering=1) isn't supported in binary mode,
                    #bufsize=1,
                    preexec_fn=os.setsid,
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                    shell=True,
                    )
                
                #for cmd in cmds:
                #    cp.stdin.write(cmd.encode('utf-8')+b'\n')
                #    if input:
                #        if isinstance(input,str): input = input.encode('utf-8')
                #        cp.stdin.write(input+b'\n')
                #        input = b''
                #    cp.stdin.flush()
                  
                try:
                    input = cmds[0].encode('utf-8')
                    outs, errs = cp.communicate(input=input,timeout=timeout)
                except subprocess.TimeoutExpired:
                    cp.kill()
                    outs, errs = cp.communicate()
                #self.channel.allStdoutBuf.append(outs)
                #self.channel.allStderrBuf.append(errs)
                self.channel.addStdoutData(outs)
                self.channel.addStderrData(errs)                
                self.channel.close()
        else:
            # not invoke shell
            self.channel = POpenChannel(self,None,timeout)
            for command in cmds:
                # it is recommended to pass args as a sequence.... If shell is True, 
                # it is recommended to pass args as a string rather than as a sequence.
                args = shlex.split(command)
                if  ('|' in args) : raise SSHScriptError('| works only in shell mode, consider to run with $$',501)
                if  ('>' in args) : raise SSHScriptError('> not works in $',502)
                logger.debug(f'subprocess.Popen: {args}')
                cp = subprocess.Popen(args,
                    # 會引起  RuntimeWarning: line buffering (buffering=1) isn't supported in binary mode,
                    #bufsize=1,
                    env=os.environ.copy(),
                    stdin=subprocess.PIPE,stderr=subprocess.PIPE,stdout=subprocess.PIPE,
                    shell=invokeShell)

                # implement stdin, and timeout (default to 600)
                timeout = self.sshscript._timeout or 600

                # outs,errs are bytes
                try:
                    outs, errs = cp.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    cp.kill()
                    outs, errs = cp.communicate()
                self.stdin = cp.stdin
                self.channel.addStdoutData(outs)
                self.channel.addStderrData(errs)
            #多行時，$.stdout, $.stderr是所有的總和
            if self.inWith:
                # 不invoke shell，卻inWith，好像沒意義
                # __exit__ will call self.channel.close()
                pass
            else:
                # self.channel.close() will not call  self.channel.recv()
                self.channel.recv()
                self.channel.close()
                if self.channel.stderr and self.sshscript._paranoid:
                    raise SSHScriptError(self.channel.stderr)
    
    def execBySSH(self,invokeShell,deepCall):
        (ssId,cmd,_globals,_locals) = self.args

        # provide value of $.username, $.port, $.host
        self.host = self.sshscript.host;
        self.username = self.sshscript.username;
        self.port = self.sshscript.port
        
        cmd = self.evalCommand()

        #hasMultipleLines = '\n' in cmd
        
        cmds = [x.strip() for x in cmd.split('\n')]
        cmds = [x for x in cmds if (x and not x.startswith('#'))]
        # 只要有with,一定是invokeShell(with ${} same as with $${})
        if self.inWith: invokeShell = True

        # implement stdin, and timeout (default to 60)
        timeout = self.sshscript._timeout or 60            

        client = self.sshscript.client if deepCall else self.sshscript._client
        if invokeShell:
            self.invokeShell = True
            logger.debug(f'executing in shell: {cmd}')
            # $${...}
            # REF: https://stackoverflow.com/questions/6203653/how-do-you-execute-multiple-commands-in-a-single-session-in-paramiko-python/6203877#6203877
            
            self.channel = ParamikoChannel(self,client, timeout)
            for command in cmds:
                self.channel.sendline(command)# write to queue
                self.channel.wait()
            
            loop.run_until_complete(self.channel.waitio(1))
            if not self.inWith:
                self.channel.close()

        else:
            # hasMultipleLines:
            # ${....}
            self.channel = ParamikoChannel(self,None, timeout)
            for command in cmds:
                logger.debug(f'executing {command}')
                # The paramiko documentation says:
                # "using exec_command or invoke_shell without a pty will ever have data on the stderr stream."
                # So, we always need not a pty.
                stdin, stdout,stderr = client.exec_command(command,get_pty=0,timeout=self.sshscript._timeout)
                self.stdin = stdin
                self.channel.addStdoutData(stdout.read())
                self.channel.addStderrData(stderr.read())
            # self.channel.close() will not call  self.channel.recv()
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
                
