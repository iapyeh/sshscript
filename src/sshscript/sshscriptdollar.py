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
from logging import DEBUG
import warnings
import __main__
import shutil
import paramiko
import socket
import termios
import tty
import traceback
try:
    from .sshscripterror import SSHScriptError, getLogger
    from .sshscriptchannel import POpenChannel, ParamikoChannel
except ImportError:
    from sshscripterror import SSHScriptError, getLogger
    from sshscriptchannel import POpenChannel, ParamikoChannel
logger = getLogger()
try:
    import pty
except ImportError:
    # pty is not available on Windows
    pty = None
## @{...} (in $)
pvarS = re.compile('\@\{(.+?)\}')
## f" and f' strings
fpqoute1 = re.compile(r'[fr]"(?:\\.|[^"\\])*"',re.M) # f"",r"" include escape \"
fpqoute2 = re.compile(r"[fr]'(?:\\.|[^'\\])*'",re.M) # f'',f'' include escape \'

## replace $.stdout, $.stderr to _c.stdout, _c.stderr, $.host     

pstd = re.compile('\$\.([a-z]+)')
def pstdSub(m):
    post = m.group(1)
    pre = ''
    if post in SSHScriptDollar.exportedProperties:
        return f'{pre}_c.{post}'
    elif post in __main__.SSHScriptExportedNames:
        return f'{pre}_sshscript_in_context_.{post}'
    elif post in __main__.SSHScriptExportedNamesByAlias:
        return f'{pre}_sshscript_in_context_.{__main__.SSHScriptExportedNamesByAlias[post]}'
    #elif post in SSHScriptClsExportedFuncs:
    #    return f'{pre}SSHScript.{post}'
    elif post == 'break':
        return f'_sshscript_in_context_._{post}'
    else:
        # SSHScript.inContext's property
        return f'{pre}_sshscript_in_context_.{post}'

class SSHScriptDollar(object):
    ## v1.1.14 add "exitcode", "channel"
    exportedProperties = set(['stdout','stderr','stdin','exitcode','channel'])
    ## aka $shell-commmand , or coverted "_c"
    def __init__(self,sshscript,cmd=None,globals=None,locals=None,inWith=False,fr=0):
        ## got value when __call__()
        cmd = cmd.strip()
        
        if fr == 1:
            self.fCommand, self.rCommand = 1,0
        elif fr == 2:
            self.fCommand, self.rCommand = 0,1
        elif cmd.startswith('f"') or cmd.startswith("f'"):
            self.fCommand, self.rCommand = 1,0
        elif cmd.startswith('r"') or cmd.startswith("r'"):
            self.fCommand, self.rCommand = 0,1
            cmd = cmd[2:-1]
        else:
            self.fCommand, self.rCommand = 0,0

        self.args = (sshscript,cmd,globals,locals)
        self.sshscript = sshscript #執行的脈絡下的 sshscript instance
        self.cp = None # got value if run by subprocess and inWith
        self._stdout = lambda: ""
        self._stderr = lambda: ""
        self._rawstdout = lambda: ""
        self._rawstderr = lambda: ""
        self.stdin = None
        self.exitcode = None
        self.inWith = inWith
        self.shellToRun = None
        self.wrapper = None
        self.bufferedOutputData = b''
        self.bufferedErrorData = b''
        # set os.environ['NO_PTY']='1' to disable pty
        global pty
        self.usePty = pty and os.environ.get('NO_PTY','') == ''
        # subpress warnings
        self.mute = os.environ.get('MUTE_WARNING')
    
    @property
    def stdout(self):
        return self._stdout()
    @property
    def stderr(self):
        return self._stderr()

    @property
    def rawstdout(self):
        return self._rawstdout()
    @property
    def rawstderr(self):
        return self._rawstderr()

    @property
    def waitingInterval(self):
        ## v2.0 CMD_INTERVAL and SSH_CMD_INTERVAL renamed to OUTPUT_TIMEOUT and SSH_OUTPUT_TIMEOUT
        return float(os.environ.get('OUTPUT_TIMEOUT',os.environ.get('CMD_INTERVAL',0.5))) 
    
    @property
    def waitingIntervalSSH(self):
        return float(os.environ.get('SSH_OUTPUT_TIMEOUT',os.environ.get('SSH_CMD_INTERVAL',self.waitingInterval)))

    @property
    def commandTimeout(self):
        return float(os.environ.get('CMD_TIMEOUT',60))

    @property
    def commandTimeoutSSH(self):
        return float(os.environ.get('SSH_CMD_TIMEOUT',self.commandTimeout))

    def log(self, msg, *args):
        logger.log(DEBUG,  msg, *args)
    
    def __call__(self,isTwodollars=False):
        global context
        
        ## reset self.sshscript's stdout and stderr
        if self.sshscript.host:
            self.execBySSH(isTwodollars)
            ## assign self to be the "lastDollar" of owner SSHScriptSession instance
            self.sshscript._lastDollar = self
            ## necessary for this instance to be put in "with context"
            if self.inWith:
                ## self.channel is ParamikoChannel  instance
                return self.channel
            else:
                return self
        else:
            self.execBySubprocess(isTwodollars)
            ## assign self to be the "lastDollar" of owner SSHScriptSession instance
            self.sshscript._lastDollar = self
            if self.inWith:
                ## self.channel is POpenChannel instance
                return self.channel
            else:
                return self
    
    def evalCommand(self):
        ## common utility for execBySSH and  execBySubprocess
        ## every command should be one-line command
        (_,cmd,_globals,_locals) = self.args
        def pvarRepl(m):
            c = m.group(1)
            if pstd.search(c):
                ## repleace $.stdout to _c.stdout
                c = pstd.sub(pstdSub,c)
            ## 有時候$@{...} eval出來的不是str
            return f'{eval(c,_globals,_locals)}'

        ## pretty print for logging
        _cmds = ['  ' +x for x in cmd.splitlines() if x]
        if len(_cmds) > 1:
            self.log(f'eval:')
            for _cmd in _cmds:self.log(_cmd)
        else:
            self.log(f'eval:{cmd}')

        if self.fCommand:
            def pqouteRepl(m):
                # 這比較不太可能eval出來的不是str
                return eval(m.group(0),_globals,_locals)
            ## $f' ... ' or $f''' .... '''
            cmd = fpqoute1.sub(pqouteRepl,cmd)
            cmd = fpqoute2.sub(pqouteRepl,cmd)
        elif self.rCommand:
            pass
        else:
            ## eval @{py-var} in $shell-command
            ## f-string mixing r-string is not allowed
            cmd = pvarS.sub(pvarRepl,cmd)

            """
                # mix 格式，複雜不會比較好
                # pvarS.sub 會替換$.stdout為_c.stdout,所以在送之前先
                quotes = {}
                def pqouteSub34(m):
                    # 只替換內容中有 $.stdout等特殊內容的字串
                    fr,quote,content = m.groups()
                    if not pstd.search(content):
                        return m.group(0)
                    key = f'#____{fr}_{hash(content)}{random.random()}____#'
                    quotes[key] = m.group(0)# (fr,quote,content)
                    return key
                cmd = pqoute3.sub(pqouteSub34,cmd)
                cmd = pqoute4.sub(pqouteSub34,cmd)
                cmd = pvarS.sub(pvarRepl,cmd)
                print('b cmd=',cmd)            
                for key,content in quotes.items():
                    cmd = cmd.replace(key,content)
                print('cmd=',cmd)
            """

        cmds = [x.lstrip() for x in cmd.splitlines() if x.lstrip()]
        return cmds

    def execBySubprocess(self,isTwodollars):
        cmds = self.evalCommand()
        ## only with-dollar and two-dollars can assing custom shell by "#!/shell"
        if self.inWith or isTwodollars:            
            shellToRun = None
            if len(cmds) and cmds[0].startswith('#!'):
                shellToRun = cmds.pop(0)[2:].strip()

            ## prepare shell command
            if not shellToRun:
                shellToRun = os.environ.get('SHELL')
                if not shellToRun:
                    if sys.platform == 'win32':
                        shell = shutil.which('pwsh') + (' -i' if self.inWith else ' -noni') +' -nol -ExecutionPolicy RemoteSigned'
                    else:
                        shellToRun = shutil.which('bash')                    
                    if shellToRun is None:
                        raise RuntimeError('no shell command found')
            
            self.log(f'[subprocess] run shell {shellToRun}')
            ## arguments for shell, such as '-r --login'
            shArgs = os.environ.get('SHELL_ARGUMENTS')
            if shArgs:
                self.log(f'[subprocess] shell arguments: {shArgs}')
                shellToRun += ' ' + shArgs

            self.shellToRun = shellToRun

            ## prepare popen command
            if sys.platform == 'win32':
                args = shell
            else:
                args = shlex.split(shellToRun)
            
            ## v2.0
            ## only with-dollar would show the "prompt"
            #if self.usePty and self.inWith:
            ## both two-dollars and with-dollar would show the "prompt"
            if self.usePty:
                ##  ref: https://errorsfixing.com/run-interactive-bash-in-dumb-terminal-using-python-subprocess-popen-and-pty/
                ##  ref: https://stackoverflow.com/questions/19880190/interactive-input-output-using-python
                ##  ref: https://github.com/python/cpython/blob/main/Lib/pty.py
                ## master for reading, slave for writing
                ## we need "prompt" for interactive shell, for prompt to show, stdin be a pty is the key

                ## work, has prompt, stdout and stderr are telled
                ##  but python console is in stderr, python's stdout are in stdout
                ##
                masterFd,slaveFd = pty.openpty()
                self.log(f'opening {args} with pty for with-dollar')
                ## should use this, otherwise in CKJ environment something would be wrong
                environ = os.environ
                #keys = sorted(os.environ.keys())
                #for k in keys:
                #    v = os.environ.get(k)
                #    if k in ('TERM_PROGRAM',): continue
                #    if k in ('PWD','LANG'):
                #        environ[k] = v
                #    print('=======>',[k,v])
                cp = subprocess.Popen( args,
                    ## don't enable this, since it was forced to use /bin/sh
                    shell=False,
                    stdin=slaveFd,stdout=subprocess.PIPE,stderr=slaveFd,
                    ##  Run in a new process group to enable bash's job control.
                    #preexec_fn=os.setsid,
                    ## recommanded by python's documentation
                    start_new_session=True,
                    #text=True,
                    env=dict(environ,TERM='vt100'),
                    )
                self.channel = POpenChannel(self,cp,[cp.stdout,masterFd],masterFd,(masterFd,slaveFd)) 
            else:
                ## windows
                environ = os.environ
                masterFd,slaveFd = zip(os.pipe(),os.pipe())
                cp = subprocess.Popen(args,
                    stdin=subprocess.PIPE,stdout=slaveFd[0],stderr=slaveFd[1],
                    # Run in a new process group to enable bash's job control.
                    #preexec_fn=os.setsid, # not working on Windows
                    env=dict(environ,TERM='vt100'),
                    )                
                self.channel = POpenChannel(self,cp,masterFd,slaveFd)

           
            try:
                self.channel.sendline(cmds)
            #except subprocess.CalledProcessError as exc:
            #    self.log(f'[subprocess]error={exc.output}')
            except Exception as e:
                if isinstance(e,SSHScriptError):
                    ## self.exitcode will be assigned to shell's exitcode
                    self.channel.close()
                    ## re-assign exitcode to exitcode of the executed command
                    self.exitcode = e.code
                raise 
            else:
                if not self.inWith:
                    ## wait for commands to complete completely
                    try:
                        ## at least one second
                        self.channel.wait(max(1,self.waitingInterval))
                        ## self.channel.close() also handles careful-related issues
                        self.channel.close()
                    finally:
                        pass

        elif len(cmds):       
            ## onedollar     
            self.channel = POpenChannel(self,None,None,None,None)
            ## 不執行無謂的 #comment
            cmds = [x.lstrip() for x in cmds if x.lstrip() and (not x.startswith('#'))]
            
            ## disabled on v2.0
            #shellSpecialChars =  ('>','<','|','&',';')
            for command in cmds:
                ## execute one by one, i/o control is not necessary
                self.log(f'[subprocess]exec:{command}')
                if sys.platform  == 'win32':
                    args = command
                else:
                    args = shlex.split(command)
                
                ## this is more simple
                ret = subprocess.run(args,stderr=subprocess.PIPE,stdout=subprocess.PIPE)
                self.exitcode = ret.returncode
                ## for multiple commands, add all output to $.stdout, $.stderr
                self.channel.addStdoutData(ret.stdout)
                self.channel.addStderrData(ret.stderr)

                error = self.checkExitcode(self.exitcode,self.channel.stderr)
                if error:
                    self.channel.close()
                    raise error

            ## self.channel.close() will not call  self.channel.recv()
            ## so we need to call it here
            ## this is not interactive, so no need to create console.stdout,console.stderr
            self.channel.close()

        else:
            ## ex. $, $@{}, $f''
            self.log(f'[subprocess]nothing to do.')

    def checkExitcode(self,exitcode,mesg):
        if self.sshscript._careful and (not exitcode == 0):
            return SSHScriptError(mesg,code=exitcode)

    def execBySSH(self,isTwodollars):
        cmds = self.evalCommand()
        host = self.sshscript.host;
        ## implement stdin, and timeout (default to 60)
        ## why not => timeout = self.waitingIntervalSSH, because self.waitingIntervalSSH is the timeout of waiting outputs of a command
        #timeout = float(os.environ.get('CMD_TIMEOUT',60))             

        client = self.sshscript.client

        self.shellToRun = self.usershell = None
        if len(cmds) and cmds[0].startswith('#!'):
            self.shellToRun = self.usershell = cmds.pop(0)[2:].strip()

        '''
        This method does not return "prompt", so this method is not used.
        if 0 and shellToRun:
            ## self-assigned shell
            channel = client.get_transport().open_session()   
            ## ParamikoChannel will handle _careful-related issue        
            self.channel = ParamikoChannel(self,channel)
            self.log(f'[{host}]paramiko invokes user shell:{shellToRun}')
            channel.exec_command(shellToRun)                
            self.sshscript.touchIO()
            self.channel.wait(max(0.5,self.waitingIntervalSSH))
            ## 送# 給shell無所謂，跳過反而可能誤殺無辜
            #cmds = [x for x in cmds if (not x.startswith('#'))]
            self.channel.sendline(cmds)

            if not self.inWith:
                self.channel.updateStdoutStderr()
                self.channel.close()
                ## self.channel.close() will not call self.channel.recv()
                ## so, we need to call it here
                ## 不是互動的，沒必要產生 console.stdout,console.stderr
                #self.channel.commitIo()
                #self.channel.close()
        if shellToRun:
            ## user prefers hisown shell
            ## ParamikoChannel will handle _careful-related issue        
            self.channel = ParamikoChannel(self,client)
            self.log(f'[{host}]paramiko invokes user shell:{shellToRun}')
            ## don't append '\r\n', it will cause two prompts were responsed by ssh server
            ## don't call sendline, we have to make prompt be responsed befere calling sendline
            self.channel.send(shellToRun+'\n')
            ## get prompt again, wait extra 2 seconds to encure the new shell command has completed before getting its prompt
            #self.channel.wait(2)
            #self.channel.getPrompt()   
            self.channel.sendline(cmds)
            if not self.inWith:
                self.channel.updateStdoutStderr('shellToRun')
                self.channel.send('exit\n') ## exit user's custome shell
                self.channel.close()
        '''
        if (self.inWith or isTwodollars):
            ## REF: https://stackoverflow.com/questions/6203653/how-do-you-execute-multiple-commands-in-a-single-session-in-paramiko-python/6203877#6203877
            ## client will call invoke_shell in ParamikoChannel
            ## ParamikoChannel will handle _careful-related issue
            self.log(f'[{host}]paramiko calls invoke_shell()')
            self.channel = ParamikoChannel(self,client)

            if len(cmds):
                try:
                    self.channel.sendline(cmds)
                except Exception as e:
                    if isinstance(e,SSHScriptError):
                        ## self.exitcode will be assigned to shell's exitcode
                        self.channel.close()
                        ## re-assign exitcode to exitcode of the executed command
                        self.exitcode = e.code
                    raise 

            if self.inWith:
                ## we are not checking self.exitcode here, because an interactive shell
                ## would check it after every command
                pass
            else:
                self.channel.updateStdoutStderr('not self.inWith')
                ## this would assign value of self.exitcode
                self.channel.close()
                error = self.checkExitcode(self.exitcode,self.channel.stderr)
                if error: raise error
        else:
            ## one-dollar
            self.channel = ParamikoChannel(self,None)
            for command in cmds:
                self.log(f'[{host}]paramiko exec_command:{command},timeout={self.commandTimeoutSSH}')
                ## The paramiko documentation says:
                ## "using exec_command or invoke_shell without a pty will ever have data on the stderr stream."
                ## So, we always need not a pty.
                #assert client._transport.is_active()
                stdin, stdout,stderr = client.exec_command(command,get_pty=0,timeout=self.commandTimeoutSSH)
                self.stdin = stdin
                endtime = time.time() + self.commandTimeoutSSH
                self.channel.addStdoutData(stdout.read())
                self.channel.addStderrData(stderr.read())
                ## to do: currently the execution time is limited to 60 seconds
                ##        user should set os.environ['CMD_TIMEOUT'] to change it.
                ##        should allow user to change the execution time easily in the future
                while not (stdout.channel.exit_status_ready()):
                    time.sleep(0.01)
                    if time.time() >= endtime:
                        ## 產生 console.stdout,console.stderr (why?)
                        self.channel.updateStdoutStderr('one-dollar timeout')
                        raise TimeoutError(f'exec_command:{command};{self.channel.stderr}')
                self.exitcode = stdout.channel.recv_exit_status()
                self.log(f'[{host}]exitcode={self.exitcode}')
                
                error = self.checkExitcode(self.exitcode,self.channel.stderr)
                if error:
                    self.channel.close()
                    raise error

            ## self.channel.close() will set up self._stdout and self._stderr
            self.channel.close()

