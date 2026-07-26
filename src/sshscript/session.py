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

## firstly patching threading.Thread
try:
    from . import patching
except ImportError:
    import patching

import ast
import threading
import paramiko
import stat
import time
import os
import sys
import traceback
import __main__
import copy
from io import StringIO
import types
import asyncio
import warnings

try:
    from .dollar import Dollar
    from .sessionwrapper import SessionWrapper,SudoConsole,SuConsole
    from .errorutils import get_logger, SSHScriptExit, SSHScriptBreak, SSHScriptException, log_debug, log_debug_8, dumpScript, listRightIndex
    ## v2.0.3 changes from sshscriptparserng to dollarparser
    from . import dollarparser
    ## this is required for user to "import *.spy"  in a .py script
    ## by onlye "import sshscriptsession" in the .py script
    from . import spyimporter

except ImportError:
    ## called directly from the same folder
    ## see above "try" block for details
    from dollar import Dollar
    from sessionwrapper import SessionWrapper,SudoConsole,SuConsole
    from errorutils import  get_logger, SSHScriptException, SSHScriptExit, SSHScriptBreak, log_debug, log_debug_8, dumpScript, listRightIndex
    import dollarparser
    import spyimporter

logger = get_logger()

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

class ConsoleWrapper:
    """
    This warp a channel to be conform the context-protocol of "with ... as"
    For example:
        $.sudo, $.su and $.enter 
        to become
        with $ as console: 
            console.su(), console.sudo(), console.enter()
    or like this:
        with $.sudo(password) as console
        to become
        with $ as console:
            with console.sudo(password) as sudoconsole:
    or 
        with $.sudo() as console:
            with console.enter():
    """
    def __init__(self,dollar,funcname,*args,**kwargs):
        """ construct the outer console """
        assert funcname in ('su','sudo','enter','shell')
        self.funcname = funcname
        
        if isinstance(dollar,ConsoleWrapper):
            self.dollar = dollar.dollar
            self.parentWrapper = dollar
        else:
            self.dollar = dollar
            self.parentWrapper = None
        ## session's _lastDollar instance
        self.channel = self.dollar.channel
        assert self.channel is not None
        self.args = args
        self.kwargs = kwargs
        self.wrapper = SessionWrapper(self)
        self.enter_count = 0
    def __enter__(self):
        ## could enter many times.
        ## eg.
        ## with $.su(...) as console:
        ##        with console:
        ##            ...
        if self.parentWrapper and self.parentWrapper.enter_count == 0:
            self.parentWrapper.__enter__()
        self.enter_count += 1
        self.wrapper.__enter__()
        self.channel.__enter__()
        ## call EnterConsole, SuConsole,...
        self.innerConsole = getattr(self.wrapper,self.funcname)(*self.args,**self.kwargs)
        self.innerConsole.__enter__()
        return self.wrapper
    enter = __enter__

    def __exit__(self,exc_type, exc_value, _traceback):
        '''
        Only 1st layer would call this __exit__
        '''
        
        #if exc_value is not None:
        #    return self.wrapper.__exit__(exc_value, _traceback)

        #assert self.enter_count >= 1
        self.enter_count -= 1
        ## EnterConsole.__exit__ etc.
        self.innerConsole.__exit__(exc_type, exc_value, _traceback)
        self.wrapper.__exit__(exc_value, _traceback)
        self.wrapper = None
        if self.parentWrapper is None:
            self.channel.__exit__(exc_type, exc_value, _traceback)
            self.channel.close()
            if self.channel.interaction_thread:
                self.channel.interaction_loop.call_soon_threadsafe(self.channel.interaction_loop.stop) 
                self.channel.interaction_thread.join()

            ## close event loop
            tasks = asyncio.all_tasks(self.channel.owner.event_loop)
            if tasks:          
                for task in tasks:
                    task.cancel()
                time.sleep(0.2)
            self.channel.owner.event_loop.call_soon_threadsafe(self.channel.owner.event_loop.stop) 
            self.channel.owner.call_thread.join()
            #if not self.channel.closed: 
        else:
            return self.parentWrapper.__exit__(exc_type, exc_value, _traceback)

    def exit(self):
        return self.__exit__(None,None,None)
    
    def __repr__(self):
        return f'ConsoleWrapper({self.funcname})'
    ##
    ##  with $.enter(...):
    ##      ...
    ##  $.exitcode <<==== this statement would request the properties of stdout, stderr and exitcode
    @property
    def exitcode(self):
        print(self.channel.closed,'<<<<<<<')
        return self.channel.exitcode
    @property
    def stdout(self):
        return self.channel.stdout
    @property
    def stderr(self):
        return self.channel.stderr

__main__.ConsoleWrapper = ConsoleWrapper

class Session(object):
    counter = 0
    def __init__(self,parent=None):
        super(Session,self).__init__()
        self.closed = False
        
        Session.counter += 1
        self.id = f"{threading.current_thread().native_id}:{Session.counter}"
        
        ## initial properties
        self._host = None
        self._port = None
        self._username = None
        self.runLocker = threading.Lock()

        self.ownerstack = None
        ## homony i/o of this thread
        self._lastIOTime = 0

        ## for su, sudo to reference (value on demand)
        self._console_info_locker = threading.Lock()
        self._console_info = None
        
        self._client = None
        self._sock =  None
        self._sftp = None

        self.blocksOfScript = None
       
        self.subsessions = []
        self.enteringThreads = []
        self.enteringThreadsLocker = threading.Lock()

        ## parent is an Session() in the parent-thread, or parent-connection
        if parent:
            assert isinstance(parent,Session)
            self.parent = parent
        else:
            self.parent = None

        ## todo: verify these two in threads
        #self._careful = parent._careful if parent else False
        self._timeout = parent._timeout if parent else None #blocking
        
        ## Line number count in total files (when showing source of multiple files)
        ## from v1.1.13, when --debug presented, don't show total count (better for debugging)
        self.lineNumberCount = 0


        self.logger = logger
        ## when exec_command() or withdollar() was called,
        ## this value was stored, so user can access its stdout, stderr and exitcode
        ## by self.stdout and self.stderr, self.exitcode
        self._lastDollar = None

        self._append_to_thread_stack()
    ## added in v2.0.3
    ## always return the session which is not connected to execute commands by subprocess at localhost
    @property
    def local_session(self):
        if self.parent:
            return self.parent.local_session
        else:
            return self

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

    #@property
    #def client(self):
    #    return self._client

    @property
    def connected(self):
        return self._client and self._client.get_transport().is_active()

    @property
    def sftp(self):
        assert self.connected
        if self._sftp is not None:
            return self._sftp
        elif self._client:
            self._sftp = self._client.open_sftp()
            return self._sftp
        else:
            return None

    @property
    def console_info(self):
        try:
            if self._console_info_locker: self._console_info_locker.acquire()
            if self._console_info is None:
                self._console_info = {}
                ##if su --help 2>&1 | grep -q -- "--pty"; then
                ##    moden linux
                ##else
                ##    legacy-linux-or-busybox or bsd
                command = 'su --help 2>&1 | grep -q -- "--pty"'
                d = Dollar(self,command)
                d(get_pty=False)
                self._console_info['is_su_pty_ok'] = d.exitcode == 0
                del d
            return self._console_info
        finally:
            if self._console_info_locker:
                self._console_info_locker.release()
                ## self._console_info_locker is required when self._console_info is None
                ## once self._console_info has values, self._console_info_locker was not required
                self._console_info_locker = None
    #@property
    #def os_name(self):
    #    return self.console_info['os_name'].lower()

    #@property
    #def is_bsd_based(self):
    #    ## macos, fedora
    #    if self.os_name in ('freebsd','darwin'):
    #        return True
    #    else:
    #        ## linux
    #        return False
    @property
    def is_su_pty_ok(self):
        return self.console_info['is_su_pty_ok']

    def defaul_get_pty(self,base_shell_for):
        if self.os_name == 'darwin':
            return True
        elif self.os_name == 'freebsd':
            if base_shell_for in ('shell','su'):
                return True
            else:
                return False
        else:
            if base_shell_for in ('shell','su'):
                return True
            else:
                return False
    '''
    def new_session(self):
        ## Why do we need this function?
        s = Session(self)
        s._console_info = self._console_info
        s._host = self._host
        s._username = self._username
        s._port = self._port
        s._client = self._client
        #s._lastDollar = self._lastDollar
        #s._sock = self._sock
        #s._socket_of_proxy_command = self._socket_of_proxy_command
        return s
    '''

    @export2Dollar
    def close_session(self):
        return self.close()

    def _append_to_thread_stack(self,the_thread=None):
        """ make this session to be the attached session in given thread."""
        if the_thread is None:
            the_thread = threading.current_thread()
        self._thread_appened_to = the_thread
        the_thread.sshscriptstack.append(self)
        '''
        if hasattr(the_thread,'sshscriptstack'):
            ## has patched thread
            the_thread.sshscriptstack.append(self)
        else:                
            ## not been patched thread
            the_thread.sshscriptstack = patching.SshscriptStack(the_thread,[self])
        '''
        return the_thread
    def _pop_from_thread_stack(self):
        """ make this session to be the attached session in given thread. """
        #if aThread is None: aThread = threading.current_thread()
        return self._thread_appened_to.sshscriptstack.pop(self)

    def __repr__(self):
        if self.connected:
            return f'<Session {self.id}:{self._host}>'
        else:
            return f'<Session {self.id}>'

    def __enter__(self):
        self.enteringThreadsLocker.acquire()
        threading.current_thread().sshscriptstack.append(self)
        #print(f'>>>>enteringThreads={threading.current_thread().sshscriptstack.stack}')
        self.enteringThreads.append(threading.current_thread())
        self.enteringThreadsLocker.release()
        return self

    def __exit__(self,*args):
        self.enteringThreadsLocker.acquire()
        idx = listRightIndex(self.enteringThreads,threading.current_thread())
        #print(f'idx= {idx}, enteringThreads={self.enteringThreads[idx].sshscriptstack.stack}')
        self.enteringThreads[idx].sshscriptstack.pop(self)
        del self.enteringThreads[idx]
        self.enteringThreadsLocker.release()
        if len(self.enteringThreads) == 0:
            ## if this session is localhost, don't close it
            ## since it's self.enteringThreads does not 
            ## contains the thread which was added in __enter__.
            ## Calls close() only when it is a remote connection.
            ## because the 1st thread in enteringThreads is 
            ## the thread which was added by parent session's connect()
            if self._client is not None:
                self.close()               
        return False

    @property    
    @export2Dollar
    def local_session(self):
        if self.parent is None: return self
        p = self
        while p.parent is not None:
            p = p.parent
        return p
    @export2Dollar('break')
    def _break(self,code=0,message=''):
        log_debug(f'break, message={message}')
        raise SSHScriptBreak(message,code)

    @export2Dollar
    def exit(self,code=0,message=''):
        log_debug(f'exit, message={message}')
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

        log_debug_8(f'{self} is going to connect {host}')

        def connectClient(host,username,password,port,policy,**kw):
            client = paramiko.SSHClient()
            ## client.load_system_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
            if policy:
                client.set_missing_host_key_policy(policy)
            client.connect(host,username=username,password=password,port=port,**kw)
            return client

        ## if this top sshscript instance already has a connection, the return a new instance (aka clone a new instance)
        ## to be the new parent session for this connection.
        subsession = Session(self)

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

        ## convert pkey_path to pkey
        if 'pkey_path' in kw and not 'pkey' in kw:
            kw['pkey'] = self.pkey(kw['pkey_path'])
            del kw['pkey_path']

        if self._client:
            ## a nested connection
            if 'proxyCommand' in kw:
                raise NotImplementedError('proxyCommand not support in a nested session')
            else:
                try:
                    subsession.runLocker.acquire(timeout=60)
                    log_debug_8(f'{self} is nestly connecting to {username}@{host}:{port}')
                    ## REF: https://stackoverflow.com/questions/35304525/nested-ssh-using-python-paramiko
                    dest_addr = (host,port)
                    local_addr = (self.host,self.port)
                    subsession._sock = self._client.get_transport().open_channel("direct-tcpip", dest_addr, local_addr)
                    subsession._client = connectClient(host,username,password,port,policy,sock=subsession._sock,**kw)
                    log_debug_8(f'{self} has connected to {username}@{host}:{port},(subsession={subsession})')
                    self.subsessions.append(subsession)
                except Exception as e:
                    ## paramiko.ChannelException, paramiko.ssh_exception.SSHException 
                    logger.warning(f'{self} failed to connect {username}@{host}:{port}, reason: {e}')
                    log_debug(traceback.format_exc())  
                    raise e
                finally:
                    subsession.runLocker.release()
        else:
            try:
                subsession.runLocker.acquire(timeout=60)
                if 'proxyCommand' in kw:
                    log_debug_8(f"{self} is connecting to {username}@{host}:{port} by proxyCommand:{ kw['proxyCommand']}")
                    subsession._sock = subsession._socket_of_proxy_command(kw['proxyCommand'])
                    del kw['proxyCommand']
                    kw['banner_timeout'] = 200000
                    kw['timeout'] = 200000
                    kw['auth_timeout' ] = 200000
                    subsession._client = connectClient(host,username,password,port,policy,sock=subsession._sock,**kw)
                else:
                    log_debug_8(f'{self} is connecting to {username}@{host}:{port}')
                    subsession._client = connectClient(host,username,password,port,policy,**kw)
            except TimeoutError as e:
                log_debug(f'{subsession} failed to connect {username}@{host}:{port}, reason: {e}')

            except Exception as e:
                ## eg.
                ## paramiko.ChannelException, paramiko.ssh_exception.SSHException 
                ## paramiko.ssh_exception.SSHException: Error reading SSH protocol banner
                log_debug(f'{subsession} error on connecting {username}@{host}:{port}, reason: {e}')
                log_debug(traceback.format_exc())
                raise e
            else:
                log_debug_8(f'{self} has connected to {username}@{host}:{port},(subsession={subsession})')
                self.subsessions.append(subsession)
            finally:
                subsession.runLocker.release()  

        ## keep alive (added from v1.1.18)
        keepAliveInterval = int(os.environ.get('KEEPALIVE_INTERVAL','60'))
        if keepAliveInterval:
            subsession._client.get_transport().set_keepalive(keepAliveInterval)

        log_debug_8(f'{subsession} keep alive interval={keepAliveInterval} seconds')

        ## auto bind to current thread
        #subsession._bind_to_thread()

        return subsession

    ## alias of connect, would be removed later
    @export2Dollar
    def open(self,*args,**kw):
        return self.connect(*args,**kw)


    ## v2.0.3 add password
    @export2Dollar
    def pkey(self,pathOfRsaPrivate,password=None):
        if self.connected:
            _,stdout,stderr = self._client.exec_command(f'cat "{pathOfRsaPrivate}"')
            exitcode = stdout.channel.recv_exit_status()
            if exitcode > 0:
                raise SSHScriptException(f'failed to get pkey from {pathOfRsaPrivate}, exitcode = {exitcode}, stderr = {stderr}')
            else:
                keyfile = StringIO(stdout.read().decode('utf8'))
                pkey = paramiko.RSAKey.from_private_key(keyfile,password)                
            return pkey
        else:
            # localhost
            try:
                with open(pathOfRsaPrivate) as fd:
                    return paramiko.RSAKey.from_private_key(fd,password)
            except FileNotFoundError:
                raise SSHScriptException(f'{pathOfRsaPrivate} not found in localhost')
    
    @export2Dollar
    def upload(self,src,dst,makedirs=False,overwrite=True):
        """
        if dst is in an non-existing directory, FileNotFoundError will be raised.
        """        
        assert self.connected, f'{self} is not connected, client={self._client}'

        src = os.path.abspath(os.path.normpath(src))
        if not os.path.exists(src):
            raise FileNotFoundError(src)
        if not os.path.isfile(src):
            raise SSHScriptException(f'uploading src "{src}" must be a file',503)
        

        remoteCwd = self.sftp.getcwd() or ''
        dst = os.path.normpath(dst)
        
       
        log_debug(f'upload {src} to {os.path.join(remoteCwd,dst)}')
        
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
                log_debug_8(f'{foldersToMake}')
                return (None,None)
    
            if len(foldersToMake):
                foldersToMake.reverse()
                for folder in foldersToMake:
                    log_debug(f'making folder: {folder}')
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

        log_debug(f'downaloading from {src} to {dst}')            
        
        self.sftp.get(src,dst)
        
        log_debug_8(f'downaloaded from {src} to {dst}')            
        return (src,dst)

    def _socket_of_proxy_command(self,argsOfProxyCommand):
        return paramiko.ProxyCommand(argsOfProxyCommand)        

    
    ## v3.0 no more globals() and locals()
    ## v3.1, run a asyncio event loop
    def async_run(self,script,vars=None,showScript=False,timeout=None):
        ## setup the event loop for running the script, and run the script in the event loop

        if timeout is not None:
            raise NotImplementedError('sshscript.run() timeout is not implemented yet')

        ## run in current thread.
        loop = asyncio.get_event_loop()
        if not loop or loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        ## v2.0 default running locals and globals to caller function's locals() and globals() 
        if vars is None:
            vars = sys._getframe(1).f_locals
        try:
            return loop.run_until_complete(self.run_in_eventloop(script,vars,showScript,timeout))
        except Exception as e:
            traceback.print_exc()
            raise
        finally:
            ## miso
            ## close event loop
            # 1. 取得當前所有還在運行的任務 (排除自己)
            tasks =  asyncio.all_tasks(loop)
            if tasks:          
                # 2. 對所有任務發送取消訊號
                for task in tasks:
                    task.cancel()
                ## 3. 給任務一點時間處理 CancelledError (這步最關鍵)
                ## 使用 return_exceptions=True 確保即使任務報錯也不會中斷 gather
                #await asyncio.gather(*tasks, return_exceptions=True)            
                time.sleep(0.2)                
            loop.call_soon_threadsafe(loop.stop) 
            loop.close()

    def run(self,script,vars=None,showScript=False,timeout=None):
        if vars is None:
            vars = sys._getframe(1).f_locals
        try:
            return self.run_in_eventloop(script,vars,showScript,timeout)
        except Exception as e:
            traceback.print_exc()
            raise
    def run_in_eventloop(self,script,vars=None,showScript=False,timeout=None):
        ## timeout:int, in seconds
        def executeScript(script,_vars,showScript=False):
            filepath = _vars.get('__file__')
            ## v2.0 auto detecting script types
            try:
                ## testing if this is a regular python script
                ast.parse(script)
            except SyntaxError:
                scriptChunk = 'import sys,threading\n' + dollarparser.convert(filepath or '<str>',script)
            else:
                ## saved content of --script output
                scriptChunk = script
            
            if showScript:
                dumpScript(scriptChunk)
                return {}


            ## write a tempory file for correctly report error in traceback infomation
            if filepath:
                if not os.path.exists(os.path.join(os.path.dirname(filepath),'__pycache__')):
                    os.mkdir(os.path.join(os.path.dirname(filepath),'__pycache__'))
                modified_path = os.path.join(os.path.dirname(filepath),'__pycache__',os.path.basename(filepath))
                with open(modified_path,'w') as fd:
                    fd.write(scriptChunk)
            else:
                modified_path = '<str>'
            

            ## v2.0.3 merge locals to globals
            exec_vars = copy.copy(_vars)

            ## add from v1.1.18, v2.0.3 changed to '__main__'
            try:
                exec_vars['__name__']
            except KeyError:
                exec_vars['__name__'] = '__main__'

            ## setup the _sshscriptstacks_ for the session
            _sshscriptstacks_ = exec_vars.get('_sshscriptstacks_')
            threading.current_thread().sshscriptstack = _sshscriptstacks_ or patching.SshscriptStack(threading.current_thread(),[self])

            exec_vars['threading']= threading
            exec_vars['types']= types
            exec_vars['Dollar'] = Dollar

            code = compile(scriptChunk, modified_path, 'exec')
            try:
                exec(code, exec_vars)  # Run the modified code inside the module's namespace
            except SSHScriptBreak:
                ## ignore this exception
                return exec_vars
            except SSHScriptExit as e:
                ## v2.0.3, same as SSHScriptExit
                raise SystemExit(e.errno)
            except SyntaxError as e:
                raise
            except SystemExit:
                raise
            except SSHScriptException:
                raise
            except Exception as e:
                traceback.print_exc()
                raise
            else:
                return exec_vars
            finally:
                pass
            
        ## v.1.18
        self.runLocker.acquire(timeout=60)
        if not self.runLocker.locked():
            raise TimeoutError('sshscript.run() require locker timeout')
        
        
        def runner(*args):
            runSession = f"{self.host}:{threading.current_thread().native_id}"
            log_debug(f"{runSession}: sshscript.run() starts")
            ret = {}
            try:
                ret['value'] = executeScript(*args)
            except SystemExit as e:
                ret['system_exit'] = e
                log_debug(f"{runSession}: sshscript.run() exits, code={e.code}")
            except SSHScriptExit as e:
                ret['exception'] = e
                ret['exitcode'] = e.errno
                log_debug(f"{runSession}: sshscript.run() exits by SSHScriptExit")
                raise
            except SSHScriptException as e:
                ret['exception'] = e
                ret['exitcode'] = e.errno
                ## 不要raise,如果raise會自動產生 traceback.print_exc()
                #raise
                sys.stderr.write(f'{type(e.message)}:{str(e.message)}')
            except Exception as e:
                ret['exception'] = e
                ## 這個讓畫面很難看,暫時取消(sshscript.py那裡也會traceback.print_exc())
                #traceback.print_exc()
                #ret['error'] = e
                log_debug(f"{runSession}: sshscript.run() error, error={e}")
            else:
                pass
            finally:
                log_debug(f"{runSession}: sshscript.run() completed")
            return ret

        ret = runner(script,vars,showScript)


        ## self.runLocker might be already released by caller because of timeout
        if self.runLocker.locked(): self.runLocker.release()
        log_debug_8(f'{self} run() release lock, locked= {self.runLocker.locked()}')
        
        if ret.get('exception'):
            raise ret['exception']
        elif ret.get('system_exit'):
            sys.exit(ret['system_exit'].code)
        else:
            log_debug(f'{self} run() complete')
            ## what is for, for next spy script?
            ret['value']['_sshscriptstacks_'] = threading.current_thread().sshscriptstack
            return ret['value']

    ## v2.0.3 added feature
    @export2Dollar
    def clear(self):
        if self._lastDollar: self._lastDollar.clear()


    def exec_command(self,cmd,*,shell=None,shell_executable=None,
                     _legacy_twodollars=False,**kw):
        """Execute one command, automatically selecting direct or shell mode.

        ``shell=None`` (the default) performs quote-aware command inspection.
        ``shell=False`` forces structured/direct execution and ``shell=True``
        forces POSIX shell execution.  ``shell='bash'`` selects and enables a
        named shell.  A list/tuple command is always direct.
        """
        if isinstance(shell,str):
            if shell_executable is not None:
                raise ValueError('use either shell="name" or shell_executable, not both')
            shell_executable = shell
            shell = True
        elif shell is not None and not isinstance(shell,bool):
            raise TypeError('shell must be None, bool, or a shell executable name')

        if isinstance(cmd,str):
            cmd = cmd.strip()
        elif isinstance(cmd,(list,tuple)):
            if shell:
                raise ValueError('list/tuple commands cannot use shell=True')
            shell = False
        else:
            raise TypeError(f'command must be str, list, or tuple, not {type(cmd).__name__}')
        if not cmd:
            raise ValueError('command must not be empty')

        if _legacy_twodollars:
            warnings.warn(
                '$$ is deprecated; use $ and automatic shell detection instead',
                DeprecationWarning,
                stacklevel=2,
            )
            shell = True

        self._lastDollar = Dollar(
            self,
            cmd,
            for_with=False,
            use_shell=shell,
            shell_executable=shell_executable,
            **kw,
        )
        self._lastDollar()
        return self._lastDollar.stdout,self._lastDollar.stderr

    ## Compatibility aliases for code generated by older parsers.
    def onedollar(self,cmd,**kw):
        warnings.warn(
            'onedollar() is deprecated; use exec_command()',
            DeprecationWarning,
            stacklevel=2,
        )
        return self.exec_command(cmd,**kw)

    def twodollars(self,cmd,**kw):
        warnings.warn(
            'twodollars() is deprecated; use exec_command(..., shell=True)',
            DeprecationWarning,
            stacklevel=2,
        )
        kw.pop('shell',None)
        return self.exec_command(cmd,shell=True,**kw)
    ## alias 
    __call__ = exec_command
    send_line = exec_command

    ## v2.0 added feature
    ## eg. "with $.shell('bash') as bash:"
    ## eg. "with $python3" => with $.shell('python3')
    def shell(self,command=None,funcname='shell',get_pty=True,*args,**kw):
        """
        :base_shell_for:
            None: when this is for $.shell()
            name:(su,sudo,enter) when this shell is as base shell of $.sudo(), $.su(), $.enter()
                it is not necessary to return an instace of ConsoleWrapper
        :kw:
            keyword arguments for ConsoleWrapper, then InnerConsole (SuConsole, SudoConsole, EnterConsole)
        """
        ## sudo,su,enter should set get_pty when calling this function
        assert funcname in ('shell','enter','su','sudo')
        
        if command:
            command = command.strip()
        else:
            command = 'bash -i'

        if isinstance(self._lastDollar,ConsoleWrapper) and not self._lastDollar.channel.closed:
            ## inner with
            self._lastDollar = ConsoleWrapper(self._lastDollar,funcname,False,*args,**kw)
        else:
            dollar = Dollar(self,command,for_with=True)
            ## self._lastDollar is an instance of SSHChannel or POpenChannel
            dollar(get_pty=get_pty)
            self._lastDollar = ConsoleWrapper(dollar,funcname,False,*args,**kw)
        return self._lastDollar
    ## set alias
    withdollar = shell

    ## v2.0 added feature
    def su(self,username,password=None,expect=None,initials=None,shell:bool=True,login=True,get_pty=True):
        """
        shell:str, the shell command to run as the base-shell
        """
        command = SuConsole.get_command(self,username,login,get_pty)
        if shell:
            self.shell(None,get_pty=get_pty)
            self._lastDollar = ConsoleWrapper(self._lastDollar,'su',username,password=password,expect=expect,initials=initials,login=login,command=command)
        else:
            dollar = Dollar(self,command,for_with=True)
            dollar(get_pty=get_pty)
            self._lastDollar = ConsoleWrapper(dollar,'su',username,password=password,expect=expect,initials=initials,login=login,command=False)

        return self._lastDollar
    ## v2.0 added feature
    def sudo(self,password=None,username=None,expect=None,initials=None,shell:bool=True,login=True,get_pty=True):
        command=SudoConsole.get_command(self,username,login)
        if shell:
            self.shell(None,get_pty=get_pty)
            self._lastDollar = ConsoleWrapper(self._lastDollar,'sudo',username=username,password=password,expect=expect,initials=initials,login=login,command=command)
        else:
            dollar = Dollar(self,command,for_with=True)
            dollar(get_pty=get_pty)
            self._lastDollar = ConsoleWrapper(dollar,'sudo',username=username,password=password,expect=expect,initials=initials,login=login,command=False)

        return self._lastDollar
        '''
            self.shell('bash',get_pty=get_pty)
            ## command=None is passed to SudoConsole()
            command = None
        else:
            self.shell(command,base_shell_for='sudo',get_pty=get_pty)
            ## command=False is passed to SudoConsole(); it is "False", not "None"
            command = False
        return self._lastDollar
        #return ConsoleWrapper(self._lastDollar,'sudo',password=password,expect=expect,initials=initials,command=command,login=login,username=username)
        '''
    ## $.enter
    def enter(self,command,expect=None,password=None,exit=None,shell:bool=True,get_pty=True,prompt=None):
        ## when base_shell is True, self.shell would assign value of self._lastDollar
        ## by assign to self._lastDollar, the $.exitcode and $.stderr would be available after "exit" the "enter"
        ## ensure having self._lastDollar (channel of ssh or popen)
        if shell:
            self.shell(None,get_pty=get_pty)
            self._lastDollar = ConsoleWrapper(self._lastDollar,'enter',command,expect=expect,password=password,exit=exit,prompt=prompt)
        else:
            dollar = Dollar(self,command,for_with=True)
            ## self._lastDollar is an instance of SSHChannel or POpenChannel
            dollar(get_pty=get_pty)
            command = False
            self._lastDollar = ConsoleWrapper(dollar,'enter',command,expect=expect,password=password,exit=exit,prompt=prompt)
        return self._lastDollar
        '''
            self.shell('bash',base_shell_for='enter',get_pty=get_pty)
        else:
            self.shell(command,base_shell_for='enter',get_pty=get_pty)
            command = False
        
        return self._lastDollar
        ## arguments after "enter", aka, command, expect ... are submitted to SessionWrapper.enter()
        #return ConsoleWrapper(self._lastDollar,'enter',command,expect=expect,password=password,exit=exit,prompt=prompt)
        '''
    ## delegates to self._lastDollar
    ## eg. 1st level $.wait
    @property
    def dollar(self):
        return self._lastDollar
    @property
    def stdout(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.stdout
    #@property
    #def rawstdout(self):
    #    if self._lastDollar is None: raise ValueError('no execution result yet')
    #    return self._lastDollar.rawstdout
    @property
    def stderr(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.stderr
    #@property
    #def rawstderr(self):
    #    if self._lastDollar is None: raise ValueError('no execution result yet')
    #    return self._lastDollar.rawstderr    
    @property
    def exitcode(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.exitcode
    def wait_for_silent(self,seconds,max_seconds=0):
        return self._lastDollar.wait_for_silent(seconds,max_seconds)
    wait = wait_for_silent
    def wait_for_output(self,timeout=0,silent=False):
        return self._lastDollar.wait_for_output(timeout,silent)

    @export2Dollar
    def close(self):

        ## don't allow to be called multiple times
        if self.closed: return 

        for subsession in reversed(self.subsessions):
            subsession.close()

        log_debug_8(f'{self} was closed')
        log_debug_8(f'{self} is closing {self.username}@{self.host}:{self.port}')
        self.closed = True
        ## auto unbind to current thread
        self._pop_from_thread_stack()

        ## don't acquire self.runLocker, since this might be called by self.run()
        ##self.runLocker.acquire(timeout=60)

        ## remove self from parent session        
        if self.parent:
            try:
                self.parent.subsessions.remove(self)
            except ValueError:
                log_debug( f"{self} is not in parent {self.parent}'s subsessions, called twice?")
            else:
                log_debug_8( f"{self} is removed from parent {self.parent}'s subsessions")
          
        if self._sftp:
            self._sftp.close()
            self._sftp = None
           
        if self._client:
            self._client.close()
            self._client = None
            if isinstance(self._sock,paramiko.proxy.ProxyCommand):
                ## wait for the openssl process to finish, important for proxyCommand not become a zombie
                while (not self._sock.closed) and (self._sock.process.poll() is None):
                    time.sleep(0.1)
                try:
                    self._sock.process.stdout.close()
                    self._sock.process.stderr.close()
                    self._sock.process.stdin.close()
                except:
                    ## maybe the bug has fixed (still existing on paramiko v3.5.0)
                    pass
            #elif self._sock:
            #    ## 1st connecting target might have no self._sock
            #    self._sock.close()
            self._sock = None

        log_debug(f'{self} has closed {self.username}@{self.host}:{self.port}')
        self._host = None
        self._port = None
        self._username = None
        
    ## alias
    disconnect = close    
    def __del__(self):
        self.close()
