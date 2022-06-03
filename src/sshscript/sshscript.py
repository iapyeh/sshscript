#!/usr/bin/env python3
from paramiko import SSHClient,AutoAddPolicy
from io import StringIO
import paramiko
import os, sys, traceback, time, re, random, glob
import logging
import hashlib
import queue, threading
import subprocess, shlex, socket
import __main__
try:
    from sshscriptdollar import SSHScriptDollar
    from sshscripterror import SSHScriptError, SSHScriptExit
except ImportError:
    from .sshscriptdollar import SSHScriptDollar
    from .sshscripterror import SSHScriptError, SSHScriptExit
"""
# replace @{var} in py scripts
pvarS = re.compile('(\b?)\@\{(.+?)\}',re.S)
"""
# replace @{var} in $shell-command
pvar = re.compile('(\b?)\@\{(.+)\}')
# replace $.stdout, $.stderr to _c.stdout, _c.stderr, $.host in $LINE
pstd = re.compile('(\b?)\$\.([a-z]+)\b?')
#pstd = re.compile('^([ \t]*?)\$\.([a-z]+)\b?') 不能加入^,否則在字串中的$.stdout會無法匹配
# looking for @include( to self.open( in Py
#pAtInclude = re.compile('^( *?)\@include\(([^\)]+)\)',re.M)
pAtInclude = re.compile('^( *?)\$.include\(([^\)]+)\)',re.M)
# line startswith $, such as $${, ${, $shell-command but not $.
pDollarWithoutDot = re.compile('^\$[^\.][\{\w]?')
# line startswith $shell-command , $$shell-command , $@{py-var} , $$#! , $<space>abc
# but not ${, $${
pDollarCommand = re.compile('^\$(?!\$?\{)') # will match 
# replace @open( to self.open( in Py
pAtFuncS = re.compile('^([\t ]*?)\@(\w+\()',re.M)
# find $.stdin =
pStdinEquals = re.compile('^[\t ]*?(\$\.stdin[\t ]*=)',re.M)
# find "with $shell-command"
pWithDollar = re.compile('^[\t ]*?with +\$[^\.]',re.M)
# replace "with @open", "with @subopen"
#pAtFuncSWith = re.compile('^([\t ]*?)with([\t ]+)\@(\w+\()',re.M)
pAtFuncSWith = re.compile('^([\t ]*?)with([\t ]+)\$\.(\w+\()',re.M)
# find with ... as ...
pAsString = re.compile(' +as +([^\:]+)\:')
# find with ... } as ... ; curly brackets
pCurlyBracketsAsString = re.compile('^[\t ]*?\}( +as +([^\:]+)\:.*)$',re.M)
# find  ... }
pCurlyBrackets = re.compile('^[ \t]*?\}')
# """ and ''' blocks
pqoute1 =re.compile('("{3})(.+?)"{3}',re.S)
pqoute2 =re.compile("('{3})(.+?)'{3}",re.S)

class DummyLogger:
    def __init__(self,level=2) -> None:
        # 1:debug, 2:info, 3:warning, 4:error
        self.level = level
    def debug(self,msg):
        if self.level == 1 : print(f'[DEBUG]{msg}')
    def info(self,msg):
        if self.level <= 2 : print(f'[INFO]{msg}')
    def warning(self,msg):
        if self.level <= 3 : print(f'[WARNING]{msg}')        
    def error(self,msg):
        if self.level <= 4 : print(f'[ERROR]{msg}')        

logger = DummyLogger()

class LineGenerator:
    def __init__(self,lines):
        self.lines = lines
        self.cursor = -1
        self.savedCursor = None
    def next(self):
        self.cursor += 1
        if self.cursor >= len(self.lines):
            raise StopIteration()
        return self.lines[self.cursor]
    def save(self):
        self.savedCursor = self.cursor
    def restore(self):
        assert self.savedCursor is not None
        self.cursor = self.savedCursor
    def __next__(self):
        return self.next()
    def __iter__(self):
        return self

# replace $.stdout, $.stderr to _c.stdout, _c.stderr
# replace $.open(), $.subopen() to SSHScript.inContext.
pQuoted = re.compile('\(.*\)')
# exported to $.<func>, such as $.open, $.close, $.exit
SSHScriptExportedFuncs = set()
#SSHScriptClsExportedFuncs = set() # "include" only, now.
def pstdSub(m):
    pre,post = m.groups()
    if post in SSHScriptExportedFuncs:
        return f'{pre}SSHScript.inContext.{post}'
    elif post in SSHScriptDollar.exportedProperties:
        return f'{pre}_c.{post}'
    #elif post in SSHScriptClsExportedFuncs:
    #    return f'{pre}SSHScript.{post}'
    else:
        # SSHScript.inContext's property
        return f'{pre}SSHScript.inContext.{post}'

def export2Dollar(func):
    try:
        SSHScriptExportedFuncs.add(func.__name__)
    except AttributeError:
        # classmethod
        #assert isinstance(func,classmethod)
        #SSHScriptClsExportedFuncs.add(func.__func__.__name__)
        raise
    return func

class SSHScript(object):
    # this SSHScript() which in context of @method in py
    inContext = None
    # a lookup table of instances of SSHScript by id
    items = {}

    @classmethod
    def connect(cls,host,port=22,username=None,password=None,**kw):
        client = SSHClient()
        #client.load_system_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
        # 允許連線不在know_hosts檔案中的主機
        client.set_missing_host_key_policy(AutoAddPolicy())
        #3.連線伺服器
        client.connect(host,port=port,username=username,password=password,**kw)
        return client
    
    @classmethod
    def include(cls,prefix,abspath):
        if not os.path.exists(abspath):
            raise SSHScriptError(f'{abspath} not fournd, @include("{abspath}") failed',401)
        with open(abspath) as fd:
            content = fd.read()
        #find prefix
        prefixLen = 0
        for c in content:
            if c == ' ': prefixLen += 1
            elif c == '\t': prefixLen += 1
            else: break
        # omit leading prefix
        rows = []
        for line in content.split('\n'):
            # skip "__export__ = [ "line
            if line.replace(' ','').startswith('__export__=['):
                continue
            rows.append(prefix + line[prefixLen:])
        script =  '\n'.join(rows)
        
        if pAtInclude.search(script):
            # do include again (nested @include)
            scriptPath = abspath
            def pAtIncludeSub(m):
                prefix, path = m.groups()
                abspath = os.path.join(os.path.dirname(scriptPath),eval(path))
                content = SSHScript.include(prefix,abspath)
                return content
            script = pAtInclude.sub(pAtIncludeSub,script)

        return script

    def __init__(self,parent=None):

        if parent is not None: assert isinstance(parent,SSHScript)

        # initial properties
        self.host = None
        self.port = None
        self.username = None

        self._previousSshscriptInContext = None
        # SSHScript.inContext 一開始是第一個創建的SSHScript instance，
        # 其次的SSHScript instance，只有在open之後才會成為SSHScript.inContext
        if SSHScript.inContext is None:
            SSHScript.inContext = self
            self._previousSshscriptInContext = self       
        
        self.id = f'{time.time()}{int(1000*random.random())}'
        SSHScript.items[self.id] = self
        self._client = None
        self._shell = None
        self._sftp = None

        self.blocksOfScript = None

        # nested sessions
        self._sock = None
        self.parentSession = parent
        self.subSession = None
        if parent: parent.subSession = self 

        # settings when exec command (see client.exec_command)
        self._paranoid = parent._paranoid if parent else False
        #self._pty = parent._pty if parent else False
        self._timeout = parent._timeout if parent else None #blocking
        
        # current dir
        #self.pwd = '.'
        # 累積的行號(多檔案showScript時使用)
        self.lineNumberCount = 0

        # value of self.cachedStdin
        #self.__stdinForNextExecution = None
    
    @property
    def client(self):
        return self.subSession.client if self.subSession else self._client

    #@property
    #def deepPwd(self):
    #    return self.subSession.deepPwd if self.subSession else self.pwd

    def __repr__(self):
        return f'(SSHScript:{id(self)}@{self.host})'

    def getSocketWithProxyCommand(self,argsOfProxyCommand):
        return paramiko.ProxyCommand(argsOfProxyCommand)        
    
    @export2Dollar
    def exit(self,code=0):
        raise SSHScriptExit(code)
    
    @export2Dollar
    def open(self,host,username=None,password=None,port=22,**kw):
        # host 可以是 username@hostname 的格式
        if '@' in host:
            username,host = host.split('@')
        
        # 檢查是否是 subopen (讓open是subopen的alias,使用者可以都一直使用open，不使用subopen)
        if self._client is not None:
            # 但不能是自己連接自己
            if host == self.host:
                raise SSHScriptError(f'Self connection from {host} to {host} is not allowed',502)
            else:
                return self.subopen(host,username,password,port,**kw)
        
        # self.host　是用來判斷有沒有ssh連線的依據（如果沒有則是subprocess)
        self.host = host
        self.port = port
        self.username = username
        
        # 必須也檢查 self.parentSession.client，因為在同一個script中，可能上一個session已經關掉，
        # 但是在parse時，將此段放在不同的 sshscript instance中，如unittest6()的情況
        # (這樣的結構在此情況下不是很漂亮，可能有未知的情況)
        if self.parentSession and self.parentSession._client:
            if 'proxyCommand' in kw:
                raise NotImplementedError('proxyCommand not support in nested session')
            else:
                logger.debug(f'{self.id} nested openning {self.username}@{self.host}:{self.port}')
                # REF: https://stackoverflow.com/questions/35304525/nested-ssh-using-python-paramiko
                vmtransport = self.parentSession._client.get_transport()
                dest_addr = (host,port)
                local_addr = (self.parentSession.host,self.parentSession.port)
                self._sock = vmtransport.open_channel("direct-tcpip", dest_addr, local_addr)
                self._client = SSHScript.connect(host,port,username,password,sock=self._sock,**kw)
        else:
            if 'proxyCommand' in kw:
                logger.debug(f'{self.id} openning {self.username}@{self.host}:{self.port} by {kw["proxyCommand"]}')
                self._sock = self.getSocketWithProxyCommand(kw['proxyCommand'])
                del kw['proxyCommand']
                self._client = SSHScript.connect(host,port,username,password,sock=self._sock,**kw)
            else:
                logger.debug(f'{self.id} openning {self.username}@{self.host}:{self.port}')
                self._client = SSHScript.connect(host,port,username,password,**kw)

        self._previousSshscriptInContext = SSHScript.inContext
        SSHScript.inContext = self
    
        return self
    
    @export2Dollar
    def subopen(self,host,username=None,password=None,port=22,**kw):
        # enter a new channel
        if '@' in host: username,host = host.split('@')
        nestedSession = SSHScript(self)
        nestedSession.open(host,username,password,port,**kw)
        return nestedSession
    
    @export2Dollar
    def paranoid(self,yes):
        self._paranoid = yes
    
    # protocol of "with subopen as "
    def __enter__(self):
        return self
    # protocol of "with subopen as "
    def __exit__(self,*args):
        self.close() # close all subsession if any
    
    @export2Dollar
    def close(self,depthClose=False):
        # 除非指定depthClose,否則只關閉最底下的那層
        if self.subSession:
            self.subSession.close(depthClose)
            if not depthClose: return
        
        if self._sock:
            self._sock.close()
            self._sock = None
        
        if self._client:
            logger.debug(f'{self.id} closing {self.username}@{self.host}:{self.port}')
            self._client.close()
            self._client = None
        
        if self._shell:
            self._shell.close()
            self._shell = None

        if self.parentSession:
            # signal parent that this subSession has closed
            self.parentSession.subSession = None

        if self._sftp:
            self._sftp.close()
            self._sftp = None

        self.host = None
        self.port = None
        self.username = None

        SSHScript.inContext = self._previousSshscriptInContext
        logger.debug(f'restore  SSHScript.inContext to {SSHScript.inContext}')        

    def __del__(self):
        self.close(True)
        del SSHScript.items[self.id]

    #def getRsaKeyAtPath(self,pathOfRsaPrivate):
    @export2Dollar
    def getkey(self,pathOfRsaPrivate):
        #pathOfRsaPrivate = f'/home/{$.username}/.ssh/id_rsa'
        if self.host:
            _,stdout,_ = self._client.exec_command(f'cat "{pathOfRsaPrivate}"')
            keyfile = StringIO(stdout.read().decode('utf8'))
            return paramiko.RSAKey.from_private_key(keyfile)
        else:
            with open(pathOfRsaPrivate) as fd:
                return paramiko.RSAKey.from_private_key(fd)
    
    
    @export2Dollar
    def timeout(self,v):
        self._timeout = float(v)
    

    @property
    def sftp(self):
        if self._sftp is None:
            self._sftp = self.client.open_sftp()
        return self._sftp

    @export2Dollar
    def upload(self,src,dst,makedirs=False,overwrite=True):
        """
        if dst is in an non-existing directory, FileNotFoundError will be raised.
        """
        if self.subSession:
            return self.subSession.upload(src,dst)

        if not src.startswith('/'):
            raise SSHScriptError(f'uploading src "{src}" must be absolute path',503)
        
        if not dst.startswith('/'):
            raise SSHScriptError(f'uploading dst "{dst}" must be absolute path',504)
        
        
        logger.debug(f'upload {src} to {dst}')

        # check exists of dst folders
        if makedirs:
            def checking(dst,foldersToMake):
                dstDir = os.path.dirname(dst)
                try:
                    stat = self.sftp.stat(dstDir)
                except FileNotFoundError:
                    foldersToMake.append(dstDir)
                    return checking(dstDir,foldersToMake)
                return foldersToMake
            foldersToMake = checking(dst,[])
            if len(foldersToMake):
                foldersToMake.reverse()
                for folder in foldersToMake:
                    self.sftp.mkdir(folder)
                    logger.debug(f'mkdir {folder}')
        
        if not overwrite:
            try:
                self.sftp.stat(dst)
                raise SSHScriptError(f'{dst} already existed',403)
            except FileNotFoundError:
                pass
        self.sftp.put(src,dst)

    @export2Dollar
    def download(self,src,dst):

        if self.subSession:
            return self.subSession.downaload(src,dst)

        if not src.startswith('/'):
            raise SSHScriptError(f'downloading src "{src}" must be absolute path',505)
        
        if not dst.startswith('/'):
            raise SSHScriptError(f'downloading dst "{dst}" must be absolute path',506)
        
        logger.debug(f'downaload from {src} to {dst}')            
        
        self.sftp.get(src,dst)

    def parseScript(self,script,initLine=None,_locals=None,quotes=None):
        # parse script at top-level session
        scriptPath = _locals.get('__file__') if _locals else __file__
        def pAtIncludeSub(m):
            prefix, path = m.groups()
            abspath = os.path.join(os.path.abspath(os.path.dirname(scriptPath)),eval(path))
            content = SSHScript.include(prefix,abspath)
            return content
        
        def pqouteSub(m):
            quote,content = m.groups()
            hash = hashlib.md5(content.encode('utf8'))
            key = f'#____{hash.hexdigest()}____#'
            quotes[key] = (quote,content)
            return key

        # expend @include()
        script = pAtInclude.sub(pAtIncludeSub,script)
        
        #store triple-quotes content
        script = pqoute1.sub(pqouteSub,script)
        script = pqoute2.sub(pqouteSub,script)
        # replace with @open( to "with open("
        script = pAtFuncSWith.sub('\\1with SSHScript.inContext.\\3',script)
        # replace @open( to open (example)
        script = pAtFuncS.sub('\\1SSHScript.inContext.\\2',script)
        listOfLines = script.split('\n')
        # listOfLines: [string]
        lines = LineGenerator(listOfLines)
        # lines is a generator
        self.blocksOfScript = []

        # leadingIndent is the smallest leadingIndent of given script
        leadingIndent = -1
        rows = []
        #codeStarted = False

        def getShellCommandsInMultipleLines(lines):
            # multiple lines ${
            # ...... 此中間的格式不拘，indent也不拘，但leading space/tab 會被去掉
            # } 必須單獨一行
            rowsInCurlyBrackets = []
            while True:
                try:
                    nextLine = next(lines)
                except StopIteration:
                    raise SSHScriptError('unclosed with ${',403)
                # 尋找 } (必須在單獨一行的開頭；前面有space, tabOK)
                m = pCurlyBrackets.search(nextLine)
                if m:  break
                # expand $.stdout, $.(var) etc
                #cmd = pstd.sub('\\1_c\\2',nextLine.lstrip())
                cmd = pstd.sub(pstdSub,nextLine.lstrip())
                rowsInCurlyBrackets.append(cmd)
            return self.parseScript('\n'.join(rowsInCurlyBrackets),_locals=_locals,quotes=quotes)

        while True:
            try:
                if initLine:
                    line = initLine
                    initLine = None
                else:
                    line = next(lines)
            except StopIteration:
                break
            else:            
                # i = index of the 1st no-space char of this line
                i = 0
                for idx,c in enumerate(line):
                    if c != ' ' and c != '\t':
                        i = idx
                        break

                # initial assignment to leadingIndent
                # at the 1st non-empty line, use its indent as top-level indent(leadingIndent)
                if leadingIndent == -1 and line.strip():
                    leadingIndent = i

                # 這段script從去掉leadingIndent之後的那一個字元開始處理
                # 所以若有某script全部都有indent（共同indent）,則該indent會被忽略
                # i 在此之下是去除leadingIndent之後的index
                i -= leadingIndent 

                # stripedLine 是去掉共同indent之後該行的內容
                stripedLine = line[leadingIndent:]
                # indent是這一行去除共同indent之後的indent
                indent = stripedLine[:i]
                # j 是不計with時，那一行第一個有用字元的位置
                j = i 
                
                if stripedLine.rstrip() == '':
                    rows.append(stripedLine)
                    continue
                
                
                # 多行的${}, $${}內的內容（暫存用）
                shellCommandLines = []

                # 檢查是否是 with 開頭的 block "with $shell-command"
                # 不包括其他的，例如 "with @open(" 取代之後的 "with SSHScript.inContext ..."
                #prefixedByWith = False
                asPartOfWith = False
                
                #
                # 前處理
                #

                # "with $shell-command as fd", "with ${multiple lines} as fd", "with $${multiple lines} as fd"
                if pWithDollar.search(stripedLine):
                    # find "as ..."
                    m = pAsString.search(stripedLine)
                    # 調整 j 的位置
                    stripedLineWithoutWith = stripedLine[i+4:].lstrip()
                    j =  (len(stripedLine) - len(stripedLineWithoutWith))
                    if m:
                        asPartOfWith = m.group(0) # the " as ..." part
                        # 把 as ... 從$指令中去掉（必須放在取得 j 值之後）
                        stripedLine = stripedLine[:m.start()].rstrip()
                    else:
                        # multiple lines "with", for example: ${
                        # ...... 此中間的格式不拘，indent也不拘，但leading space/tab 會被去掉
                        # } 必須單獨一行
                        rowsInCurlyBrackets = []
                        while True:
                            # 故意不catch StopIteration，當作找不到結束的"as ..."時候的exception
                            try:
                                nextLine = lines.next()
                            except StopIteration:
                                raise SSHScriptError('Can not find "as" for "with" command',402)
                            # 尋找 } as .... (必須在單獨一行的開頭；前面有space, tabOK)
                            m = pCurlyBracketsAsString.search(nextLine)
                            if not m:
                                # expand $.stdout, $.(var) etc
                                #cmd = pstd.sub('\\1_c\\2',nextLine.lstrip())
                                cmd = pstd.sub(pstdSub,nextLine.lstrip())
                                rowsInCurlyBrackets.append(cmd)
                                continue
                            asPartOfWith = m.group(1) # the " as ..." part
                            break
                        shellCommandLines.extend(self.parseScript('\n'.join(rowsInCurlyBrackets),_locals=_locals,quotes=quotes))
                
                #
                # 逐行處理開始
                #
                
                # this is a comment line
                if stripedLine[j] == '#': 
                    rows.append(stripedLine) 

                # support $shell-command or "with $shell-command"
                # ＄,$$, ${, $${, $shell-command，但不是$.開頭
                elif pDollarWithoutDot.search(stripedLine[j:]) or (asPartOfWith and stripedLine[j] == '$'):
                    # leading lines of ${} or $${} (multiple lines, and must multiple lines)
                    # in single line is not supported ("with ${} as fd" is not supported)
                    if stripedLine[j+1:].startswith('{') or  stripedLine[j+1:].startswith('${'):
                        
                        ## invoke shell: $${
                        #invokeShell = 1 if stripedLine[j+1:].startswith('${') else 0
                        
                        ## 改為只要有兩個 $$ 就是 invoke shell（不必是 $${), 但是不能是分開的 $  $
                        invokeShell = 1 if stripedLine[j+1:].startswith('$') else 0

                        # first line is the content after ${ or $${ , aka omitting ${ or $${ 
                        inlineScript = [stripedLine[j+3:]] if invokeShell else [stripedLine[j+2:]]
                        if len(shellCommandLines):
                            # 已經在上面的with檢查中取得內容
                            inlineScript.extend(shellCommandLines) 
                        else:
                            try:
                                c = lines.cursor
                                shellCommandLines = getShellCommandsInMultipleLines(lines)
                            except SSHScriptError as e:
                                if e.code == 403:
                                    print('--- dump start ---')
                                    print('\n'.join(lines.lines[c:lines.cursor + 1]))
                                    print('--- dump end ---')
                                    raise e
                            inlineScript.extend(shellCommandLines)
                        
                        if len(inlineScript): # 廢話？看起來是一定成立
                            cmd = '\n'.join(inlineScript)
                            # 分成先建立SSHScriptDollar物件,再執行的2步驟。先取名為 __c 而不是 _c ，
                            # 此__c執行之後，再指定成為 _c 
                            # 因為命令中可能會呼叫 _c（例如 $.stdout)，係指前次執行後的_c,這樣才不會混淆。
                            # 但是__c執行有錯的時候，_c 又必須為本次執行的__c，所以放到try:finally當中
                            # 這樣可以在SSHScriptError丟出之前把_c設定為__c
                            indentOfTryBlock = '    '
                            rows.append(f'{indent}try:')
                            # strip triple-quote
                            tripleQuote = '' if cmd.lstrip().startswith('#____') else '"""'
                            rows.append(f'{indent}{indentOfTryBlock}__b = {tripleQuote}{cmd} {tripleQuote}')
                            rows.append(f'{indent}{indentOfTryBlock}__c = SSHScriptDollar(None,__b,locals(),globals(),inWith={1 if asPartOfWith else 0})')
                            rows.append(f'{indent}{indentOfTryBlock}__ret = __c({invokeShell})')
                            rows.append(f'{indent}finally:')
                            rows.append(f'{indent}{indentOfTryBlock}_c = __c')
                            if asPartOfWith:
                                rows.append(f'{indent}with __ret {asPartOfWith}')

                    # single line $shell-comand or $$shell-command
                    # this is always run by SSHScript.inContext (an instance of SSHScript)
                    elif pDollarCommand.search(stripedLine[j:]):
                        # 前後要留空白，避免 "與"""混在一起
                        invokeShell = 1 if stripedLine[j+1] == '$' else 0
                        cmd = stripedLine[j+2:] if invokeShell else stripedLine[j+1:]
                        
                        # expand $.stdout, $.(var) etc in cmd
                        if pvar.search(stripedLine):
                            #cmd = pstd.sub('\\1_c\\2',cmd.lstrip())
                            cmd = pstd.sub(pstdSub,cmd.lstrip())
                        
                        rows.append(f'{indent}try:')
                        indentOfTryBlock = '    '
                        # strip triple-quote
                        tripleQuote = '' if cmd.lstrip().startswith('#____') else '"""'
                        rows.append(f'{indent}{indentOfTryBlock}__b = {tripleQuote}{cmd} {tripleQuote}')
                        rows.append(f'{indent}{indentOfTryBlock}__c = SSHScriptDollar(None,__b,locals(),globals(),inWith={1 if asPartOfWith else 0})')
                        rows.append(f'{indent}{indentOfTryBlock}__ret = __c({invokeShell})')
                        rows.append(f'{indent}finally:')
                        rows.append(f'{indent}{indentOfTryBlock}_c = __c')

                        if asPartOfWith:
                            # 注意：此處還沒寫完，因為moreIndent必須是下一行的indent才行
                            rows.append(f'{indent}with __ret {asPartOfWith}')
                    else:
                        raise SyntaxError(f'failed to parse "{stripedLine}" from "{[stripedLine[j:]]}"')
                else:
                    # expand $.stdout, $.(var) etc
                    #rows.append(pstd.sub('\\1_c\\2',stripedLine))
                    rows.append(pstd.sub(pstdSub,stripedLine))

        return rows

    
    def run(self,script,varLocals=None,varGlobals=None,showScript=False):

        _locals = locals()
        if varLocals is not None:
            _locals.update(varLocals)

        _globals = globals()
        if varGlobals is not None:
            _globals.update(varGlobals)

        quotes = {}
        if isinstance(script, str):
            rows = self.parseScript(script,_locals=_locals,quotes=quotes)
            if len(rows):
                # close this block
                self.blocksOfScript.append('\n'.join(rows))        
        
        assert  self.blocksOfScript is not None
        #print([type(item) for item in self.blocksOfScript])        
        
        assert _locals.get('self')
        def dumpScriptItem(scriptChunk):
            for idx, line in enumerate(scriptChunk.split('\n')):
                print(f'{str(idx+1).zfill(3)}:{line}')
            traceback.print_exc()

        for scriptChunk in self.blocksOfScript:
            if isinstance(scriptChunk, str):
                # restore back triple-quotes content
                for key,(quote,content) in quotes.items():
                    scriptChunk = scriptChunk.replace(key,f'{quote}{content}{quote}')

                if showScript:
                    for line in scriptChunk.split('\n'):
                        self.lineNumberCount += 1
                        print(f'{str(self.lineNumberCount).zfill(3)}:{line}')
                    continue

                try:
                    exec(scriptChunk,_globals,_locals)
                except SyntaxError as e:
                    if os.environ.get('DEBUG'):  dumpScriptItem(scriptChunk)
                    raise
                except SystemExit as e:
                    if e.code != 0:
                        traceback.print_exc()
                    else:
                        raise
                except SSHScriptError:
                    if os.environ.get('DEBUG'):  dumpScriptItem(scriptChunk)
                    raise
                except SSHScriptExit:
                    break
                except:
                    if os.environ.get('DEBUG'):  dumpScriptItem(scriptChunk)
                    raise
            elif isinstance(scriptChunk, self.__class__):
                scriptChunk.run(None,_locals,_globals,showScript=showScript)
        return _locals

def runPath(givenPaths,varGlobals=None,varLocals=None,showScript=False,showFilesOrder=False,unisession=True):
    # @givenPaths:string 
    # @showScript:bool
    # @varGlobals:dict
    # @unisession:bool, if true, use the same session(an instance of SSHScript) for all files.
    paths = []
    for path in givenPaths:
        path = os.path.abspath(path)
        # if path is a directory, add all *.spy files in it
        if os.path.isdir(path):
            # files in folder are sorted by name
            unsortedFilesInPath = list(filter(lambda x: x[-4:] == '.spy',[os.path.abspath(os.path.join(path,y)) for y in os.listdir(path)]))
        else:
            # glob.glob returns a list of files, or empty list if no file matches
            unsortedFilesInPath = glob.glob(path)
            if len(unsortedFilesInPath) == 0:
                if not os.path.exists(path):
                    # Don't raise exception, just ignore this path
                    # Because in context of sshscript, this may be a argument to the script
                    #raise RuntimeError(f'{os.path.abspath(path)} not found')
                    pass
                elif os.path.isfile(path):
                    unsortedFilesInPath.append(path)
                else:
                    raise RuntimeError(f'{os.path.abspath(path)} not supported')
        unsortedFilesInPath.sort()
        for p in unsortedFilesInPath:
            if p in paths:
                logger.debug('ignore duplicate path: %s' % p)
                continue
            paths.append(p)

    if showFilesOrder:
        for path in paths:
            print(path)
        return
    
    _locals = locals()
    _globals = globals()
    if unisession:
        session = SSHScript()
    else:
        session = None
    if varGlobals: _globals.update(varGlobals)
    if varLocals: _locals.update(varLocals)
    for file in paths:
        # 每一個檔案產生一個sshscript物件
        if not unisession:
            session = SSHScript()
        logger.debug(f'run {file}')
        absfile = os.path.abspath(file)
        with open(absfile) as fd:
            script = fd.read()

        _locals['__file__'] = absfile
        newlocals = session.run(script,_locals.copy(),_globals.copy(),showScript=showScript)
        if newlocals.get('__export__'):
            # __export__ = ['*'] will export all
            if '*' in newlocals['__export__']:
                _locals.update(newlocals)
            else:
                for key in newlocals['__export__']:
                    logger.debug(f'{absfile} export {key}')
                    _locals[key] = newlocals[key]
        if not unisession:    
            session.close()
            del session

    if unisession:    
        session.close()
        del session

def runScript(script,varGlobals=None,varLocals=None,showScript=False):
    session = SSHScript()
    _locals = locals()
    _globals = globals()
    if varGlobals: _globals.update(varGlobals)
    if varLocals: _locals.update(varLocals)
    session.run(script,varGlobals=_globals,varLocals=_locals,showScript=showScript)

def setupLogger(debug=None):
    global logger
    # silent paramiko
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    logger = logging.getLogger('SSHScript')
    if debug:
        logger.setLevel(logging.DEBUG) 
    else:
        logger.setLevel(logging.INFO) 
    handler = logging.StreamHandler(sys.stdout)
    #handler.setLevel(logging.DEBUG)    
    #handler = logging.FileHandler('test.log', 'w', 'utf-8') # or whatever
    #handler.setFormatter(logging.Formatter('%(name)s %(message)s')) # or whatever
    logger.addHandler(handler)


def main(topic,args):
    if logger is None:
        setupLogger(args.debug)
    if topic == '-f':
        runPath(args.paths,showScript=args.showScript,showFilesOrder=args.showFilesOrder)

__main__.SSHScript = SSHScript
__main__.logger = logger

def run():
    import argparse

    # REF: https://stackoverflow.com/questions/15753701/how-can-i-pass-a-list-as-a-command-line-argument-with-argparse
    parser = argparse.ArgumentParser(description='SSHScript')

    parser.add_argument('--script', dest='showScript', action='store_const',
                        const='1', default='',
                        help='show the converted python script only, no execution.')
    
    parser.add_argument('--file-order', dest='showFilesOrder', action='store_const',
                        const='1', default='',
                        help='show the files to run in order, no execution.')


    # set log level to debug
    parser.add_argument('--debug', dest='debug', action='store_const',
                        const='1', default='',
                        help='set log level to debug')

    # multiple values (requires no flag)
    # path or folder, ex. python3 sshscript unitest
    parser.add_argument(dest='paths', action='store', nargs='*',
                        help='the script file or folder of .spy files')

    #args = parser.parse_args()
    args, unknown = parser.parse_known_args()
    if len(args.paths):
        main('-f',args)
    else:
        parser.print_help()

if __name__ == '__main__':
    run()