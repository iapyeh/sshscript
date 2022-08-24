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


import os, re
import subprocess, shlex
from logging import DEBUG
import warnings
import __main__
import shutil
try:
    from .sshscripterror import SSHScriptError,getLogger
    from .sshscriptchannel import POpenChannel, ParamikoChannel
except ImportError:
    from sshscripterror import SSHScriptError,getLogger
    from sshscriptchannel import POpenChannel, ParamikoChannel
try:
    import pty
except ImportError:
    # pty is not available on Windows
    pty = None
# @{...} (in $)
pvarS = re.compile('\@\{(.+?)\}')
# f" and f' strings
fpqoute1 = re.compile(r'[fr]"(?:\\.|[^"\\])*"',re.M) # f"",r"" include escape \"
fpqoute2 = re.compile(r"[fr]'(?:\\.|[^'\\])*'",re.M) # f'',f'' include escape \'
# ' .. ', "...", r'..', r"..""
#pqoute3 = re.compile("([fr]?)(')(.+?)'",re.M)
#pqoute4 = re.compile('([fr]?)(")(.+?)"',re.M)

# $.stdout,$.stderr
pstd = re.compile('\$\.([a-z]+)')
def pstdSub(m):
    post = m.group(1)
    pre = ''
    if post in __main__.SSHScriptExportedNames:
        return f'{pre}SSHScript.getContext(1).{post}'
    elif post in SSHScriptDollar.exportedProperties:
        return f'{pre}_c.{post}'
    elif post in __main__.SSHScriptExportedNamesByAlias:
        return f'{pre}SSHScript.getContext(1).{__main__.SSHScriptExportedNamesByAlias[post]}'
    #elif post in SSHScriptClsExportedFuncs:
    #    return f'{pre}SSHScript.{post}'
    else:
        # SSHScript.inContext's property
        return f'{pre}SSHScript.getContext(1).{post}'
global loop

class SSHScriptDollar(object):
    # v1.1.13 add "exitcode", "returncode" and "channel"
    exportedProperties = set(['stdout','stderr','stdin','exitcode','returncode','channel'])
    # aka $shell-commmand , or coverted "_c"
    def __init__(self,ssId,cmd=None,globals=None,locals=None,inWith=False):
        # got value when __call__()
        self.logger = None

        cmd = cmd.strip()
        
        self.fCommand = cmd.startswith('#_____f') or cmd.startswith('f"') or cmd.startswith("f'")
        self.rCommand = cmd.startswith('#_____r') or cmd.startswith('r"') or cmd.startswith("r'")

        self.args = (ssId,cmd,globals,locals)
        self.sshscript = None #執行的脈絡下的 sshscript instance
        self.stdout = ''
        self.stderr = ''
        self.stdin = None
        self.exitcode = None
        self.inWith = inWith
        #self.hasExit = False # True if user calls exit()
        #self.invokeShell = False
        self.wrapper = None
        self.bufferedOutputData = b''
        self.bufferedErrorData = b''
        # set os.environ['NO_PTY']='1' to disable pty
        self.usePty = pty and os.environ.get('NO_PTY','') == ''
        self.waitingInterval = float(os.environ.get('CMD_INTERVAL',0.5))
        # subpress warnings
        self.mute = os.environ.get('MUTE_WARNING')

    def _log(self, level, msg, *args):
        self.logger.log(level, "[sshscript$]" + msg, *args)
    
    def __call__(self,isTwodollars=False,deepCall=True):
        ssId = self.args[0]
        
        if ssId:            
            self.sshscript = __main__.SSHScript.items[ssId]
        else:
            self.sshscript = __main__.SSHScript.getContext(1)
            assert self.sshscript is not None
            '''
            if self.sshscript is None:
                # 這個情況發生在呼叫thread時，不是使用$.thread。
                # 除了使用者的問題之外，也可能發生在像使用pytermgui這種場合。
                # 例如 ex-pytermguil.spy在ubuntu執行
                self.sshscript = __main__.SSHScript.getContextFromMainThread()
            '''
        # assign logger
        self.logger = self.sshscript.logger
        
        # reset self.sshscript's stdout and stderr
        if self.sshscript.host:
            self.execBySSH(isTwodollars,deepCall)
            # necessary for this instance to be put in "with context"
            if self.inWith:
                # self.channel is ParamikoChannel  instance
                return self.channel
            else:
                return self
        else:
            self.execBySubprocess(isTwodollars)
            if self.inWith:
                # self.channel is POpenChannel instance
                return self.channel
            else:
                return self
    
    def evalCommand(self):
        # common utility for execBySSH and  execBySubprocess
        # every command should be one-line command
        (_,cmd,_globals,_locals) = self.args
        def pvarRepl(m):
            c = m.group(1)
            if pstd.search(c):
                # repleace $.stdout to _c.stdout
                c = pstd.sub(pstdSub,c)
            # 有時候$@{...} eval出來的不是str
            return f'{eval(c,_globals,_locals)}'
        # pretty print for logging
        _cmds = ['  ' +x for x in cmd.splitlines() if x]
        prefix = ':f' if self.fCommand else (':r' if self.rCommand else '')
        if len(_cmds) > 1:
            self._log(DEBUG,f'eval{prefix}:')
            for _cmd in _cmds:self._log(DEBUG,_cmd)
        else:
            self._log(DEBUG,f'eval{prefix}:{cmd}')

        if self.fCommand:
            def pqouteRepl(m):
                # 這比較不太可能eval出來的不是str
                return eval(m.group(0),_globals,_locals)
            # $f' ... ' or $f''' .... '''
            cmd = fpqoute1.sub(pqouteRepl,cmd)
            cmd = fpqoute2.sub(pqouteRepl,cmd)
        elif self.rCommand:
            cmd = eval(cmd)
        else:
            # eval @{py-var} in $shell-command
            # f-string mixing r-string is not allowed
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

        """
        不要警告，因為無法做好
        if len(cmds):
            # deprecated warnning
            # to force 1st-line command to begin with #! if it is a shell
            knownShells = ('bash','sh','csh','tcsh','ksh','zsh','env')
            # Two cases:
            # /usr/bin/env python3 -i => should treat as a shell
            # sh a-script.sh          => should not
            bin = cmds[0].split()[-1]
            if (not bin.startswith('#!')) and (os.path.basename(bin) in knownShells):
                if not self.mute:
                    warnings.warn(f'''
                    Assigning a shell for execution should prefix it with "#!".
                    Without the prefix "#!" would be an error after verion 1.2.0.
                    For example: #!{cmds[0]}'''
                    ,UserWarning,stacklevel=0)
                cmds[0] = '#!' + cmds[0]
        """
        return cmds

    def execBySubprocess(self,isTwodollars):
        cmds = self.evalCommand()

        
        # 送# 給shell無所謂，跳過反而可能誤殺無辜
        #cmds = [x for x in cmds if x and (not x.startswith('#'))]

        # implement stdin, and timeout (default to 60)
        timeout = float(os.environ.get('CMD_TIMEOUT',60))
        
        # 如果有指定#!/shell，也必須是＄＄ or with $
        if self.inWith or isTwodollars:
            
            shell = None
            if len(cmds) and cmds[0].startswith('#!'):
                shell = cmds.pop(0)[2:].strip()

            # prepare shell command
            if not shell:
                shell = os.environ.get('SHELL')
                if shell is None:
                    shell = shutil.which('bash')
                    if shell is None:
                        raise RuntimeError('no shell command found')
            
            self._log(DEBUG,f'[subprocess]use shell {shell}')
            # arguments for shell, such as '-r --login'
            shArgs = os.environ.get('SHELL_ARGUMENTS')
            if shArgs is not None:
                self._log(DEBUG,f'[subprocess]SHELL_ARGUMENTS={shArgs}')
                shell += ' ' + shArgs

            # prepare popen command
            args = shlex.split(shell)
            self._log(DEBUG,f'[subprocess]Popen {args}')
            
            if self.usePty:
                # ref: https://errorsfixing.com/run-interactive-bash-in-dumb-terminal-using-python-subprocess-popen-and-pty/
                # ref: https://stackoverflow.com/questions/19880190/interactive-input-output-using-python
                masterFd,slaveFd = zip(pty.openpty(),pty.openpty())                
                #masterFd,slaveFd = zip([subprocess.PIPE,subprocess.PIPE],[subprocess.PIPE,subprocess.PIPE])       
                #masterFd,slaveFd = zip(os.pipe(),os.pipe())
                cp = subprocess.Popen(args,
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
            
            # open the main process is also a kind of dogin IO
            self.sshscript.touchIO()

            # wait for bash to start up
            # 等到初始IO結束後0.5second才繼續
            self.channel.wait(0.5)
            try:
                for command in cmds:
                    self.channel.wait(self.waitingInterval)
                    self.channel.sendline(command)
            except subprocess.CalledProcessError as exc:
                self._log(DEBUG,f'[subprocess]error={exc.output}')
            self.channel.wait(self.waitingInterval)
            
            if not self.inWith:
                self.channel.wait(1)
                self.channel.close()
                self.exitcode = cp.returncode
        
        elif len(cmds):            
            self.channel = POpenChannel(self,None,timeout)

            # 不執行無謂的 #comment
            cmds = [x.lstrip() for x in cmds if x.lstrip() and (not x.startswith('#'))]

            shellSpecialChars =  ('>','<','|','&',';')
            for command in cmds:
                # 這種指令是一個個執行的，因此不需要作什麼io管制
                self._log(DEBUG,f'[subprocess]exec:{command}')
                args = shlex.split(command)

                if not self.mute:
                    for char in shellSpecialChars:
                        if char in args: 
                            #raise SSHScriptError(f'char "{char}" not works in "$command"',502)
                            warnings.warn(f'''
        These symbols ('>','<','|','&',';') might not work in one-dollar commands($).
        You could consider to use two-dollars commands($$) or with-dollars commands(with $).
                            '''
                            ,UserWarning,stacklevel=0)


                cp = subprocess.Popen(args,
                    env=os.environ.copy(),
                    stdin=subprocess.PIPE,stderr=subprocess.PIPE,stdout=subprocess.PIPE,
                    shell=False)

                # outs,errs are bytes
                try:
                    outs, errs = cp.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    cp.kill()
                    outs, errs = cp.communicate()
                finally:
                    #self.exitcode = cp.poll()
                    self.exitcode = cp.wait()
                    self._log(DEBUG,f'[subprocess]$ returncode={self.exitcode}')
                
                self.stdin = cp.stdin

                #多行時，$.stdout, $.stderr是所有的總和
                self.channel.addStdoutData(outs)
                self.channel.addStderrData(errs)

            # self.channel.close() will not call  self.channel.recv()
            # so we need to call it here
            self.channel.recv()
            self.channel.close()
            #if self.channel.stderr and self.sshscript._paranoid:
            #    raise SSHScriptError(self.channel.stderr)
            if (self.exitcode is not None) and self.exitcode > 0 and self.sshscript._paranoid:
                raise SSHScriptError(self.channel.stderr)
        else:
            # 如果沒有命令要執行，啥都不必作
            # ex. $, $@{}, $f''
            self._log(DEBUG,f'[subprocess]nothing to do.')

    
    def execBySSH(self,isTwodollars,deepCall):
        # ? when deepcall is false?
        assert deepCall

        cmds = self.evalCommand()

        # provide value of $.username, $.port, $.host
        """
        self.host = self.sshscript.host;
        self.username = self.sshscript.username;
        self.port = self.sshscript.port
        """
        host = self.sshscript.host;
        # implement stdin, and timeout (default to 60)
        timeout = float(os.environ.get('CMD_TIMEOUT',60))             

        client = self.sshscript.client
        '''
        # 往下找最下層的client
        if deepCall:
            client = self.sshscript.client
            if client is None:
                # 這種情況是發生在新的下層threading執行時的情況
                client = self.sshscript.connectedParent._client
        else:
            client = self.sshscript._client
        '''

        shell = None
        if len(cmds) and cmds[0].startswith('#!'):
            shell = cmds.pop(0)[2:].strip()

        if shell:
            # two dollars commands
            channel = client.get_transport().open_session()           
            self.channel = ParamikoChannel(self,channel, timeout)
            self._log(DEBUG,f'[{host}]user shell:{shell}')                
            self.channel.channel.exec_command(shell)
            self.sshscript.touchIO()
                
            # 送# 給shell無所謂，跳過反而可能誤殺無辜
            #cmds = [x for x in cmds if (not x.startswith('#'))]
            for command in cmds:
                self.channel.wait(self.waitingInterval)
                self.channel.sendline(command)# write to queue

            if not self.inWith:
                self.channel.close()
                # self.channel.close() will not call self.channel.recv()
                # so, we need to call it here
                self.channel.recv()
                self.channel.close()

                # ret code 一般是 -1 ,這裡的條件恐怕永不會成立
                if self.exitcode > 0 and self.sshscript._paranoid:
                    raise SSHScriptError(self.channel.stderr)        

        elif (self.inWith or isTwodollars):
            #self.invokeShell = True
            # REF: https://stackoverflow.com/questions/6203653/how-do-you-execute-multiple-commands-in-a-single-session-in-paramiko-python/6203877#6203877
            
            # client will call invoke_shell in ParamikoChannel
            self._log(DEBUG,f'[{host}]call paramiko invoke_shell')
            self.channel = ParamikoChannel(self,client, timeout)
            self.sshscript.touchIO()

            # 送# 給shell無所謂，跳過反而可能誤殺無辜
            #cmds = [x for x in cmds if (not x.startswith('#'))]
            for command in cmds:
                self.channel.wait(self.waitingInterval)
                self.channel.sendline(command)# write to queue
            
            self.channel.wait(self.waitingInterval)
            
            if not self.inWith:
                self.channel.close()
                # ret code 一般是 -1 ,這裡的條件恐怕永不會成立
                if self.exitcode > 0 and self.sshscript._paranoid:
                    raise SSHScriptError(self.channel.stderr) 
        else:
            self.channel = ParamikoChannel(self,None, timeout)
            for command in cmds:
                self._log(DEBUG,f'[{host}]call paramiko exec_command:{command}')
                # The paramiko documentation says:
                # "using exec_command or invoke_shell without a pty will ever have data on the stderr stream."
                # So, we always need not a pty.
                stdin, stdout,stderr = client.exec_command(command,get_pty=0,timeout=timeout)
                self.exitcode = stdout.channel.recv_exit_status()
                self._log(DEBUG,f'exit code= {self.exitcode}')
                self.stdin = stdin
                self.channel.addStdoutData(stdout.read())
                self.channel.addStderrData(stderr.read())

            # self.channel.close() will not call self.channel.recv()
            # so, we need to call it here
            self.channel.recv()
            self.channel.close()

            # when len(cmds) ==0, self.exitcode is None
            if (self.exitcode is not None) and self.exitcode > 0 and self.sshscript._paranoid:
                raise SSHScriptError(self.channel.stderr)

        
    # protocol of "with  as "
    def __enter__(self):
        return self
    # protocol of "with  as "
    def __exit__(self,*args):
        if self.channel:
            self.channel.close()
        if self.stdin:
            self.stdin.close()
        
    '''
    Why this? and self.wait('\n')????
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
    '''

