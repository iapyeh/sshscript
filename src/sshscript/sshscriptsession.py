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
try:
    from . import sshscriptpatching
except ImportError:
    import sshscriptpatching

## testing availability of ast.unparse
import ast
try:
    ast.unparse
except AttributeError:
    try:
        import astunparse
    except ImportError:
        print('Python version less than 3.9 require "astunparse" to be installed. Please install it by "pip install astunparse"')
        raise
    else:
        setattr(ast,'unparse', astunparse.unparse)

import threading, queue
import paramiko
import stat
import time
import os
import sys
import re
import traceback
import warnings
import __main__
import copy
from io import StringIO
from logging import DEBUG, WARN
import types

## reason of "import setupLogger" in sshscriptsession: for user scrips need not to import sshscripterror by themselves
## they can only import sshscriptsession, and call sshscriptsession.setupLogger()
try:
    from .sshscriptdollar import SSHScriptDollar
    from .sshscriptchannel import GenericChannel
    from .sshscriptchannelutils import InnerConsole
    from .sshscripterror import getLogger, SSHScriptError, SSHScriptExit, SSHScriptBreak, SSHScriptError, logDebug, logDebug8
    from . import sshscriptparser
except ImportError:
    ## called directly from the same folder
    from sshscriptdollar import SSHScriptDollar
    from sshscriptchannel import GenericChannel
    from sshscriptchannelutils import InnerConsole
    from sshscripterror import getLogger, SSHScriptError, SSHScriptExit, SSHScriptBreak, SSHScriptError, logDebug, logDebug8
    import sshscriptparser

logger = getLogger()

## monkey patch paramiko.Transport.set_keepalive
import weakref
def my_set_keepalive(self, interval, callback):
    """
    Turn on/off keepalive packets (default is off).  If this is set, after
    ``interval`` seconds without sending any data over the connection, a
    "keepalive" packet will be sent (and ignored by the remote host).  This
    can be useful to keep connections alive over a NAT, for example.
    :param int interval:
        seconds to wait before sending a keepalive packet (or
        0 to disable keepalives).
    """
    def _request(x=weakref.proxy(self)):
        try:
            ret = x.global_request("keepalive@lag.net", wait=False)
        except Exception as e:
            callback(e)
        else:
            return ret
    self.packetizer.set_keepalive(interval, _request)

paramiko.Transport.set_keepalive = my_set_keepalive

## looking for @include( to self.open( in Py
pAtInclude = re.compile('^( *?)\$.include\(([^\)]+)\)',re.M)
SSHScriptExportedNames = set(['sftp','client','logger']) # default to exposed properties
SSHScriptExportedNamesByAlias = {}
## expose to __main__ for sshdollar.py
__main__.SSHScriptExportedNames = SSHScriptExportedNames
__main__.SSHScriptExportedNamesByAlias = SSHScriptExportedNamesByAlias

def export2Dollar(nameOrFunc):    
    if callable(nameOrFunc):
        SSHScriptExportedNames.add(nameOrFunc.__name__)
        return nameOrFunc
    else:
        name = nameOrFunc
        def export2DollarWithName(func):
            assert callable(func)
            SSHScriptExportedNamesByAlias[name] = func.__name__
            return func
        return export2DollarWithName


class DummyLock():
    def acquire(self,*args,**kwargs):
        pass
    def release(self):
        pass
    def locked(self):
        return True

class ConsoleWrapper:
    ## wrapper for $.sudo, $.su and $.enter to with $ as console: console.su, console.sudo, console.enter
    ## 
    ## For example: 
    ##  with $ as console:
    ##       with console.sudo(password) as sudoconsole:
    ## usage:
    ## with $.sudo(password) as console
    
    ## construct the outer console

    def __init__(self,withdollar,funcname,*args,**kwargs):
        self.funcname = funcname
        self.withDollar = withdollar
        self.args = args
        self.kwargs = kwargs
    def __enter__(self):
        self.outerConsole = self.withDollar.__enter__()
        self.innerConsole = getattr(self.outerConsole,self.funcname)(*self.args,**self.kwargs)
        return self.innerConsole.__enter__()
    def __exit__(self,exc_type, exc_value, traceback):
        self.innerConsole.__exit__(exc_type, exc_value, traceback)
        self.withDollar.__exit__(exc_type, exc_value, traceback)


class SSHScriptSession(object):
    counter = 0
    
    @classmethod
    def include(cls,prefix,abspath,alreadyIncluded=None):
        if alreadyIncluded is None:
            alreadyIncluded = {}
        
        if not os.path.isfile(abspath): ## fixed v1.1.18
            raise SSHScriptError(f'{abspath} is not file, $.include("{abspath}") failed',401)
        
        ## prevent infinite loop
        try:
            alreadyIncluded[abspath] += 1
            maxInclude = int(os.environ.get('MAX_INCLUDE',100))
            if alreadyIncluded[abspath] > maxInclude:
                raise SSHScriptError(f'{abspath} have been included over {maxInclude} times, guessing this is infinite loop',404)
        except KeyError:
            alreadyIncluded[abspath] = 1
        
        with open(abspath,'rb') as fd:
            content = fd.read().decode('utf8','replace')

        ## find prefix
        prefixLen = 0
        for c in content:
            if c == ' ': prefixLen += 1
            elif c == '\t': prefixLen += 1
            else: break
        
        ## omit leading prefix
        rows = []
        for line in content.splitlines():
            ## skip "__export__ = [ "line
            if line.replace(' ','').startswith('__export__=['):
                continue
            rows.append(prefix + line[prefixLen:])
        script =  os.linesep.join(rows)
        

        if pAtInclude.search(script):
            ## do include again (nested @include)
            scriptPath = abspath
            def pAtIncludeSub(m):
                prefix, path = m.groups()
                ## limitation: the path should be a string, not a variable
                ## fixed v1.1.18
                path = eval(path).strip()
                if not path:
                    return 'pass'
                elif os.path.isabs(path):
                    abspath = path
                else:
                    abspath = os.path.join(os.path.abspath(os.path.dirname(scriptPath)),path)
                content = SSHScriptSession.include(prefix,abspath,alreadyIncluded)
                return content
            script = pAtInclude.sub(pAtIncludeSub,script)

        return script

    def __init__(self,parent=None):
        super().__init__()        
        SSHScriptSession.counter += 1
        self.id = f"{threading.current_thread().native_id}:{SSHScriptSession.counter}"
        
        ## initial properties
        self._host = None
        self._port = None
        self._username = None
        self.runLocker = threading.Lock()

        self.ownerstack = None
        ## homony i/o of this thread
        self._lastIOTime = 0
        
        self._client = None
        self._sock =  None
        self._sftp = None

        self.blocksOfScript = None
       
        self.subsessions = []

        ## parent is an SSHScriptSession() in the parent-thread, or parent-connection
        if parent:
            assert isinstance(parent,SSHScriptSession)
            self.parent = parent
        else:
            self.parent = None

        ## todo: verify these two in threads
        self._careful = parent._careful if parent else False
        self._timeout = parent._timeout if parent else None #blocking
        
        ## Line number count in total files (when showing source of multiple files)
        ## from v1.1.13, when --debug presented, don't show total count (better for debugging)
        self.lineNumberCount = 0


        self.logger = logger
        ## when onedollar(), twodollars(), withdollar were called,
        ## this value was stored, so user can access its stdout, stderr and exitcode
        ## by self.stdout and self.stderr, self.exitcode
        self._lastDollar = None

        logDebug(f'{self} was created')

    @property
    def session(self):
        return self

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self,v):
        self._host = v

    @property
    def username(self):
        return self._username
    
    @username.setter
    def username(self,v):
        self._username = v

    @property
    def port(self):
        return self._port
    
    @port.setter
    def port(self,v):
        self._port = v

    @property
    def client(self):
        return self._client

    @property
    def connected(self):
        return self.client and self.client.get_transport().is_active()

    @export2Dollar
    def bind(self,func):
        if isinstance(func,threading.Thread):
            aThread = func
            ## has patched thread
            if hasattr(aThread,'sshscriptstack'):
                ## why, because that if we has not do this when user calls session.bin(threading.current_thread())
                ## it might mess up the context of "$" (by inserting a session which is not sub-session of current session)
                del aThread.sshscriptstack.stack[:]
                
                aThread.sshscriptstack.stack.append(self)
            ## not been patched thread
            else:                
                aThread.sshscriptstack = sshscriptpatching.SshscriptStack(aThread,[self])
            return aThread
        else:
            assert callable(func)
            def wrapper(*args, **kwargs):
                ## replace the stack of current thread to a new instance of sshscriptstack
                restoreId = threading.current_thread().sshscriptstack.pushLayer([self]) 
                try:
                    ret = func(*args, **kwargs)
                finally:
                    ## restore the stack of current thread to the original instance of sshscriptstack
                    threading.current_thread().sshscriptstack.popLayer(restoreId)
                return ret
            return wrapper

    @property
    def sftp(self):
        assert self.connected
        if self._sftp is not None:
            return self._sftp
        elif self.client:
            self._sftp = self.client.open_sftp()
            return self._sftp
        else:
            return None

    @property
    def stdout(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.stdout
    @property
    def rawstdout(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.rawstdout
    @property
    def stderr(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.stderr
    @property
    def rawstderr(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.rawstderr
    
    @property
    def exitcode(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.exitcode

    def __repr__(self):
        if self._host:
            return f'<SSHScriptSession {self.id}:{self._host}>'
        else:
            return f'<SSHScriptSession {self.id}>'
    
    def __del__(self):
        if self._client: self.close()

    ## protocol of "with subopen as "
    def __enter__(self):
        return self

    ## protocol of "with subopen as "
    def __exit__(self,*args):
        self.close() ## close all subsession if any
        ## since this __exit__() was called, this means that this session is connected by "with $.connect()"
        ## so, let's pop this session out of the owner sshscriptstack
        ## by doing so, we don't need to add "_sshscriptstack_.pop()" at the bottom of the "with" block
        if self.ownerstack is not None: self.ownerstack.pop()
  
    ## V2 disabled, use $.logger instead
    #@export2Dollar
    #def log(self, level, msg, *args):
    #    logger.log(level, "[sshscript] %s" % msg, *args)

    @export2Dollar
    def thread(self,*args,**kw):
        ## from v2.0, thread has been patched
        kw['_sshscript_session_'] = self
        return threading.Thread(*args,**kw)
    
    @export2Dollar('break')
    def _break(self,code=0,message=''):
        logDebug(f'break, message={message}')
        raise SSHScriptBreak(message,code)

    @export2Dollar
    def exit(self,code=0,message=''):
        logDebug(f'exit, message={message}')
        raise SSHScriptExit(message,code)

    @export2Dollar
    def connect(self,host,username=None,password=None,port=22,policy=None,**kw):
        """
        v2: 
            when host is in format of "username@host", then the second parameter would set to password, 
            which means user can call this function like:
            $.connect('user@host',password) instead of $.connect('user@host',password=password)
        """
        ## host might be in format of "username@hostname"
        if '@' in host:
            if username and password is None:
                password = username
            username,host = host.split('@')

        logDebug8(f'{self} is going to connect {host}')

        ## disabled in v2.0
        #if host == self.host:
        #    self.log(WARN,f'{self} is connecting from {host} to {host}')
        #    raise SSHScriptError(f'{host} self-connection makes no sense',502)

        def connectClient(host,username,password,port,policy,**kw):
            client = paramiko.SSHClient()
            ## client.load_system_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
            if policy:
                client.set_missing_host_key_policy(policy)
            client.connect(host,username=username,password=password,port=port,**kw)
            return client

        ## if this top sshscript instance already has a connection, the return a new instance (aka clone a new instance)
        ## to be the new parent session for this connection.
        subsession = SSHScriptSession(self)

        ## self.host was used in .spy to check if it is a remote connection or 
        ## a local subprocess.
        subsession._host = host
        subsession._port = port
        subsession._username = username
        
        ## user can set policy=0 to disable client.set_missing_host_key_policy
        if policy is None:
            ## allow connect to host not which is in known_hosts
            policy = paramiko.AutoAddPolicy()

        ## keep alive (added from v1.1.18);(todo: "implement" in sub-session)
        inactive_callback = kw.get('inactive_callback')
        if inactive_callback: del kw['inactive_callback']

        if self.client:
            ## a nested connection
            if 'proxyCommand' in kw:
                raise NotImplementedError('proxyCommand not support in a nested session')
            else:
                try:
                    subsession.runLocker.acquire(timeout=60)
                    logDebug8(f'{self} is nestly connecting to {username}@{host}:{port}')
                    ## REF: https://stackoverflow.com/questions/35304525/nested-ssh-using-python-paramiko
                    vmtransport = self.client.get_transport()
                    dest_addr = (host,port)
                    local_addr = (self.host,self.port)
                    subsession._sock = vmtransport.open_channel("direct-tcpip", dest_addr, local_addr)
                    subsession._client = connectClient(host,username,password,port,policy,sock=subsession._sock,**kw)
                    logDebug8(f'{self} has connected to {username}@{host}:{port},(subsession={subsession})')
                    self.subsessions.append(subsession)
                except Exception as e:
                    ## paramiko.ChannelException, paramiko.ssh_exception.SSHException 
                    logger.warn(f'{self} failed to connect {username}@{host}:{port}, reason: {e}')
                    logDebug(traceback.format_exc())  
                    raise e
                finally:
                    subsession.runLocker.release()
        else:
            try:
                subsession.runLocker.acquire(timeout=60)
                if 'proxyCommand' in kw:
                    logDebug8(f"{self} is connecting to {username}@{host}:{port} by proxyCommand:{ kw['proxyCommand']}")
                    subsession._sock = subsession.getSocketWithProxyCommand(kw['proxyCommand'])
                    del kw['proxyCommand']
                    kw['banner_timeout'] = 200000
                    kw['timeout'] = 200000
                    kw['auth_timeout' ] = 200000
                    subsession._client = connectClient(host,username,password,port,policy,sock=subsession._sock,**kw)
                else:
                    logDebug8(f'{self} is connecting to {username}@{host}:{port}')
                    subsession._client = connectClient(host,username,password,port,policy,**kw)
            except Exception as e:
                ## eg.
                ## paramiko.ChannelException, paramiko.ssh_exception.SSHException 
                ## paramiko.ssh_exception.SSHException: Error reading SSH protocol banner
                logDebug(f'{subsession} failed to connect {username}@{host}:{port}, reason: {e}')
                logDebug(traceback.format_exc())
                raise e
            else:
                logDebug8(f'{self} has connected to {username}@{host}:{port},(subsession={subsession})')
                self.subsessions.append(subsession)
            finally:
                subsession.runLocker.release()  

        ## keep alive (added from v1.1.18)
        keepAliveInterval = int(os.environ.get('SSHSCRIPT_KEEPALIVE_INTERVAL','60'))
        if keepAliveInterval:
            def callback(e):
                subsession.close()
                if inactive_callback: inactive_callback(subsession,e)
            ## make a new callback with specified subsession and inactive callback
            callback_func = types.FunctionType(callback.__code__,{'subsession':subsession,'inactive_callback':inactive_callback}, callback.__name__, callback.__defaults__, callback.__closure__)    
            subsession._client.get_transport().set_keepalive(60,callback_func)

        logDebug8(f'{subsession} keep alive interval={keepAliveInterval} seconds')

        return subsession

    ## alias of connect, would be removed later
    @export2Dollar
    def open(self,*args,**kw):
        return self.connect(*args,**kw)

    @export2Dollar
    def careful(self,yes=None):
        if yes is None: return self._careful
        else: self._careful = True if yes else False

    @export2Dollar
    def pkey(self,pathOfRsaPrivate):
        if self.client:
            _,stdout,stderr = self.client.exec_command(f'cat "{pathOfRsaPrivate}"')
            exitcode = stdout.channel.recv_exit_status()
            if exitcode > 0:
                raise SSHScriptError(f'failed to get pkey from {pathOfRsaPrivate}, exitcode = {exitcode}, stderr = {stderr}')
            else:
                keyfile = StringIO(stdout.read().decode('utf8','replace'))
                pkey = paramiko.RSAKey.from_private_key(keyfile)                
            return pkey
        else:
            # localhost
            with open(pathOfRsaPrivate) as fd:
                return paramiko.RSAKey.from_private_key(fd)

    @export2Dollar
    def upload(self,src,dst,makedirs=False,overwrite=True):
        """
        if dst is in an non-existing directory, FileNotFoundError will be raised.
        """        
        assert self.connected, f'{self} is not connected, client={self.client}'

        src = os.path.abspath(os.path.normpath(src))
        if not os.path.exists(src):
            raise FileNotFoundError(src)
        if not os.path.isfile(src):
            raise SSHScriptError(f'uploading src "{src}" must be a file',503)
        

        remoteCwd = self.sftp.getcwd() or ''
        dst = os.path.normpath(dst)
        
        if sys.platform == 'win32':
            ## recorrect back, since ftp accecpt /
            dst = dst.replace('\\','/')        

        ## cancelled in v1.1.18    
        #if not dst.startswith('/') and not self.mute:
        #    warnings.warn(f'''uploading dst "{dst}" is not absolute path, would be {os.path.join(remoteCwd,dst)}''',UserWarning,stacklevel=0)
        
        logDebug(f'upload {src} to {os.path.join(remoteCwd,dst)}')
        
        ## check exists of dst folders
        srcbasename = os.path.basename(src)
        dstbasename = os.path.basename(dst)
        if makedirs:
            ## v1.1.12
            ## In this case, suppose given name is folder, not a file
            ## If need to create folder, all given path would be created
            ## ex. upload c0-test.txt
            ## The next 3 lines are valid:
            ##  dst is  '/home/iap/sshscriptuploadtest/nonexist1/nonexist2/nonexist3/c0-test.txt'
            ##  dst is  '/home/iap/sshscriptuploadtest/nonexist1/nonexist2/nonexist3'
            ##  dst is  '/home/iap/sshscriptuploadtest/nonexist1/nonexist2/nonexist3/'
            ## The next line might not what we expect:
            ##  dst is  '/home/iap/sshscriptuploadtest/nonexist1/nonexist2/nonexist3/test.txt'
            ## because it results in:
            ## '/home/iap/sshscriptuploadtest/nonexist1/nonexist2/nonexist3/test.txt/c0-test.txt'
            ## after v1.1.13，if given path has same file extension, it was considered to be a file
            # , not considered to be a folder. 
            ## (see unittest/c0.spy)
            if not dstbasename == srcbasename:
                if not os.path.splitext(srcbasename)[1] == os.path.splitext(dstbasename)[1]:
                    ## given dst is a folder
                    dst = f'{dst}/{srcbasename}'

            def checking(dst,foldersToMake):
                dstDir = os.path.dirname(dst)
                ## fixed on v1.1.8 for relative-path to work with makedirs=1
                if dstDir:
                    try:
                        stat = self.sftp.stat(dstDir)
                    except FileNotFoundError:
                        foldersToMake.append(dstDir)
                        return checking(dstDir,foldersToMake)
                    except:
                        return traceback.format_exc()
                return foldersToMake

            ## check un-existing folder(from down to top; suppose last one is a file)
            foldersToMake = checking(dst,[])
            if isinstance(foldersToMake,str):
                logDebug8(f'{foldersToMake}')
                return (None,None)
    
            if len(foldersToMake):
                foldersToMake.reverse()
                for folder in foldersToMake:
                    logDebug(f'making folder: {folder}')
                    self.sftp.mkdir(folder)
        else:
            ## cases:
            ## 1. basename are the same
            ## 2. basename are not the same：
            ##    2.1 dst is a folder： dst+= basename
            ##    2.2 dst is a file
            if dstbasename == srcbasename:
                pass
            else:
                try:
                    dststat = self.sftp.stat(dst)
                except FileNotFoundError:
                    ## take dst as a file
                    pass
                else:
                    ## REF: https://stackoverflow.com/questions/18205731/how-to-check-a-remote-path-is-a-file-or-a-directory
                    if stat.S_ISDIR(dststat.st_mode):
                        ## is folder，don't call os.path.join(), because in win32, it becomes "\" 
                        ## that is not what we want for "ftp"
                        dst = f'{dst}/{srcbasename}'
                        try:
                            dststat = self.sftp.stat(dst)
                        except FileNotFoundError:
                            pass
                        else:
                            if not overwrite:
                                raise FileExistsError(f'{dst} already exists')
                    else:
                        # is file
                        if not overwrite:
                            raise FileExistsError(f'{dst} already exists')
        
        self.sftp.put(src,dst)
        
        return (src,dst)

    @export2Dollar
    def download(self,src,dst=None):
        if dst is None:
            dst = os.getcwd()

        assert self.connected

        ## after v1.1.13, no more down to self.subSession for getting "client"

        ## cancelled in v1.1.18
        #if not src.startswith('/') and not self.mute:
        #    warnings.warn(f'''downloading src "{src}" is not absolute path''',UserWarning,stacklevel=0)        
        
        dst = os.path.abspath(dst)

        ## if dst is a folder, append the filename of src to dst
        if os.path.isdir(dst):
            dst = os.path.join(dst,os.path.basename(src))

        logDebug(f'downaloading from {src} to {dst}')            
        
        self.sftp.get(src,dst)
        
        logDebug8(f'downaloaded from {src} to {dst}')            
        return (src,dst)

    def getSocketWithProxyCommand(self,argsOfProxyCommand):
        return paramiko.ProxyCommand(argsOfProxyCommand)        

    def trim(self,text):
        ## strip off terminal control characters
        return GenericChannel.terminalControlCodePattern.sub('',text)

    ## v2.0
    def parseScript(self,spyscript,_locals=None):
        scriptPath = _locals.get('__file__') if _locals else __file__
        def pAtIncludeSub(m):
            prefix, path = m.groups()
            abspath = os.path.join(os.path.abspath(os.path.dirname(scriptPath)),eval(path))
            content = SSHScriptSession.include(prefix,abspath)
            return content
        ## expend $.include()
        spyscript = pAtInclude.sub(pAtIncludeSub,spyscript)
        
        pyscript = sshscriptparser.convert(spyscript)
        return [pyscript]
 
    ## v1.1.18
    def dumpScript(self,start=0,count=0):
        scriptlines = self.runningScript.splitlines()
        end = start + (count or len(scriptlines))
        for lineno in range(start,end):
            print(f'{lineno}: {scriptlines[lineno-1]})')        

    ## v1.1.18
    def errorLines(self,tb_lineno=None,count=10):
        scriptlines = self.runningScript.splitlines()        
        if tb_lineno is None:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            tb_lineno = exc_tb.tb_lineno
        start = max(0,tb_lineno - count - 1)
        end = min(len(scriptlines),tb_lineno + count)
        lines = scriptlines[start:end]
        return (tb_lineno, start+1 ,lines)

    def run(self,script,locals=None,globals=None,showScript=False,timeout=None):
        ## timeout:int, in seconds
        ## Returns the locals() (a dict) of the given script

        ## v2.0 default running locals and globals to caller function's locals() and globals() 
        if locals is None:
            locals = sys._getframe(1).f_locals
        if globals is None:
            globals = sys._getframe(1).f_globals

        ## for implementing "timeout", this task is run in an individual thread
        ## Pending: should have a way to notify the running script that it reached "Timeout" 
        def _run(script,varLocals,varGlobals,showScript=False):
            
            exce_locals = copy.copy(varLocals)

            exec_globals = copy.copy(varGlobals)

            ## add from v1.1.18
            try:
                exec_globals['__name__']
            except KeyError:
                exec_globals['__name__'] = '__sshscript__'
            
            ## v2.0 auto detecting script types
            ## noparse: if True, do not parse the script, it might already converted
            try:
                ast.parse(script)
            except SyntaxError:
                logDebug(f'{self} run() starts with .spy script')
                rows = self.parseScript(script,_locals=varLocals)
                scriptChunk = os.linesep.join(rows)
            else:
                ## saved content of --script output
                logDebug(f'{self} run() starts with regular python script')
                noparse = True
                scriptChunk = script
            
            if showScript:
                if os.environ.get('DEBUG'):
                    self.lineNumberCount = 0
                lines = scriptChunk.splitlines()
                digits = len(str(len(lines)+1))
                for line in lines:
                    self.lineNumberCount += 1
                    print(f'{line}')
                print()
                return {}
            
            ## from v1.1.18, limit the execution scope to a sub-routine
            def sandbox(scriptChunk,exec_globals,exec_locals):
                try:                   
                    self.runningScript = scriptChunk
                    ## this is funny, but it works, see the reason of "exec" below 
                    _globals = copy.copy(exec_globals)
                    _globals.update(exec_locals)
                    
                    ## _sshscriptstacks_ is the initial value for threading.current_thread().sshscriptstack 
                    ## it might be from the file(script) which run in advance of this file(script)
                    _sshscriptstacks_ = _globals.get('_sshscriptstacks_')
                    threading.current_thread().sshscriptstack = _sshscriptstacks_ or sshscriptpatching.SshscriptStack(threading.current_thread(),[self])
                    logDebug8( f'set starting session to {_sshscriptstacks_ or self}')
                    _globals['threading']= threading
                    _globals['types']= types
                    _globals['SSHScriptDollar'] = SSHScriptDollar
                    
                    ## collect return value (locals() of the script)
                    ## note: "exec(scriptChunk,_globals,_locals)" won't work
                    ##       it results more questions than it solves.
                    ##       so, we directly return _globals
                    ##       (2023/8/25, v2.0)
                    exec(scriptChunk,_globals)
                    return _globals
                except SSHScriptBreak:
                    return _globals
                except SSHScriptExit:
                    raise
                except SSHScriptError:
                    raise
                except:
                    ## for debuging v1.1.8
                    etype, evalue, exc_tb = sys.exc_info()
                    lineno = -1
                    if issubclass(etype, SyntaxError):
                        try:
                            msg, (filename, _lineno, offset, badline) = evalue.args
                        except Exception as e:
                            pass
                        else:
                            lineno = _lineno
                    if lineno == -1:
                        ## not syntaxerror or failed to get lineno. try to get lineno from traceback.
                        lines = traceback.format_exc().splitlines()
                        lines.reverse()
                        for line in lines:
                            if line.find('File "<string>"') > -1:
                                p = line.find('line')
                                q = line.find(',',p+1)
                                if q == -1:
                                    lineno = int(line[p+4:])
                                else:
                                    lineno = int(line[p+4:q])
                                break
                    if lineno > -1:
                        tb_lineno,start,lines = self.errorLines(lineno)
                        for line in lines:
                            print(f'#{str(start).zfill(3)}::{line}')
                            if start == tb_lineno:
                                print('^' * len(line))
                            start += 1
                    logDebug(f"lineno={lineno},etype={etype}")
                    raise
            return sandbox(scriptChunk,exec_globals,exce_locals)

        ## v.1.18
        self.runLocker.acquire(timeout=60)
        if not self.runLocker.locked():
            raise TimeoutError('sshscript.run() require locker timeout')
        if timeout is not None:
            timeOfTimeout = time.time() + timeout
        else:
            timeOfTimeout = 0
        
        ret = {}
        ## ensure context been initialized for this thread
        #s = self.context.get() 
        runSession = f"{self.host}:{threading.current_thread().native_id}"
        def runner(*args):
            try:
                ret['value'] = _run(*args)
            except Exception as e:
                traceback.print_exc()
                ret['error'] = e
                logDebug(f"{runSession}: sshscript.run() error, error={e}")
            else:
                pass
            finally:
                logDebug(f"{runSession}: sshscript.run() finished")
        thread = threading.Thread(target=runner,args=(script,locals,globals,showScript),name=f'sshscript-run@{self.host}',daemon=False)
        thread.start()
        
        error = None
        while True:
            ## timeout 1 seconds
            thread.join(1)
            if not thread.is_alive(): break
            elif timeOfTimeout == 0: ## no timeout
                continue
            elif time.time() > timeOfTimeout:
                ## why not kill the thread?
                error = TimeoutError(f'{self} sshscript.run() runs over {timeout} seconds')
                break
        ## self.runLocker might be already released by caller because of timeout
        if self.runLocker.locked(): self.runLocker.release()
        logDebug8(f'{self} run() release lock, locked= {self.runLocker.locked()}')

        if error or ret.get('error'):
            logDebug(f"{runSession}: sshscript.run() error={error or ret.get('error')}")
            #logDebug(f"{runSession}: script={script})")
            logDebug(f'{self} run() complete with error')
            raise error or ret.get('error')
        else:
            logDebug(f'{self} run() complete')
            ret['value']['_sshscriptstacks_'] = thread.sshscriptstack
            ## Don't do this, because the return value is not guaranteed to have "_c". 
            ## Since _c could be in locals(), not in global variables
            #self._lastDollar = ret['value']['_c']
            return ret['value']

    @export2Dollar
    def close(self):
        ## could be called multiple times
        logDebug8(f'{self} is closing {self.username}@{self.host}:{self.port}')

        for subsession in reversed(self.subsessions):
            subsession.close()

        ## don't acquire self.runLocker, since this might be called by self.run()
        #self.runLocker.acquire(timeout=60)

        ## remove self from parent session        
        if self.parent:
            try:
                self.parent.subsessions.remove(self)
            except ValueError:
                logDebug( f"{self} is not in parent {self.parent}'s subsessions, called twice?")
            else:
                logDebug8( f"{self} is removed from parent {self.parent}'s subsessions")
          
        if self._sftp:
            self._sftp.close()
            self._sftp = None
    
        if self._client:
            self._client.close()
            self._client = None


        if self._sock:
            self._sock.close()
            self._sock = None

        logDebug(f'{self} has closed {self.username}@{self.host}:{self.port}')
        self._host = None
        self._port = None
        self._username = None
        
    ## alias
    disconnect = close    

    ## v2 added feature
    def onedollar(self,script,locals=None,globals=None,timeout=None):
        script = script.strip()
        assert script[0] != '$', '"$" is not required for onedollar()'
        if locals is None:
            ## running locals and globals to caller function's locals() and globals() 
            ## reason: @{var} in the script could be evaluated to string, where "var" is local variable in caller
            locals = sys._getframe(1).f_locals
        if globals is None:
            ## running locals and globals to caller function's locals() and globals() 
            ## reason: @{var} in the script could be evaluated to string, where "var" is global variable in caller
            globals = sys._getframe(1).f_globals
        self.run('$' + script,locals,globals,timeout=timeout)
        return self.stdout,self.stderr,self.exitcode     
    
    ## v2.0 added feature
    def twodollars(self,script,locals=None,globals=None,timeout=None):
        script = script.strip()
        assert script[0] != '$', '"$" is not required for twodollars()'
        if locals is None:
            ## running locals and globals to caller function's locals() and globals() 
            locals = sys._getframe(1).f_locals
        if globals is None:
            ## running locals and globals to caller function's locals() and globals()
            globals = sys._getframe(1).f_globals
        self.run('$$' + script,locals,globals,timeout=timeout)
        return self.stdout,self.stderr,self.exitcode   

    def exec_command(self,*args,**kwargs):
        ## alias for onedollar and twodollars
        if ('shell' in kwargs) and kwargs['shell']:
            del kwargs['shell']
            return self.twodollars(*args,**kwargs)
        else:
            return self.onedollar(*args,**kwargs)
    ## alias 
    __call__ = exec_command

    ## v2.0 added feature
    def withdollar(self,shell=None,locals=None,globals=None,timeout=None):
        if locals is None:
            ## running locals and globals to caller function's locals() and globals() 
            locals = sys._getframe(1).f_locals
        if globals is None:
            ## running locals and globals to caller function's locals() and globals() 
            globals = sys._getframe(1).f_globals
        dollar = SSHScriptDollar(self,(shell or ''),locals,globals,inWith=True,fr=0)
        self._lastDollar = dollar(True) ## False = not-twodollars
        return self._lastDollar
    ## alias
    shell = withdollar
    
    ## v2.0 added feature
    def sudo(self,*args,**kwargs):
        locals = sys._getframe(1).f_locals
        globals = sys._getframe(1).f_globals
        dollar = self.withdollar(None,locals,globals)
        wrapper = ConsoleWrapper(dollar,'sudo',*args,**kwargs)
        return wrapper
    ## v2.0 added feature
    def su(self,*args,**kwargs):
        locals = sys._getframe(1).f_locals
        globals = sys._getframe(1).f_globals
        dollar = self.withdollar(None,locals,globals)
        wrapper = ConsoleWrapper(dollar,'su',*args,**kwargs)
        return wrapper
    ## v2.0 added feature
    def enter(self,*args,**kwargs):
        locals = sys._getframe(1).f_locals
        globals = sys._getframe(1).f_globals
        dollar = self.withdollar(None,locals,globals)
        wrapper = ConsoleWrapper(dollar,'enter',*args,**kwargs)
        return wrapper

       