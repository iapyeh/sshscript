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
if __package__:
    from . import patching
else:
    import patching

import ast
import threading
import paramiko
import stat
import time
import os
import sys
import __main__
import copy
from io import StringIO
import types
import asyncio
import warnings
import subprocess
import socket
from select import select
if __package__:
    from .dollar import Dollar
    from .sessionwrapper import SessionWrapper,SudoConsole,SuConsole
    from .errorutils import get_logger, SSHScriptExit, SSHScriptBreak, SSHScriptException, dumpScript, listRightIndex
    ## v2.0.3 changes from sshscriptparserng to dollarparser
    from . import dollarparser
    ## this is required for user to "import *.spy"  in a .py script
    ## by onlye "import sshscriptsession" in the .py script
    from . import spyimporter

else:
    ## called directly from the same folder
    ## see above "try" block for details
    from dollar import Dollar
    from sessionwrapper import SessionWrapper,SudoConsole,SuConsole
    from errorutils import get_logger, SSHScriptException, SSHScriptExit, SSHScriptBreak, dumpScript, listRightIndex
    import dollarparser
    import spyimporter

## setup logger
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

## 建立可重複 close 的 ProxyCommand
_PROXY_TERMINATE_TIMEOUT = 2.0
_PROXY_KILL_TIMEOUT = 2.0
_TRANSPORT_JOIN_TIMEOUT = 2.0
class _IdempotentProxyCommand(paramiko.ProxyCommand):
    def __init__(self, command_line):
        super().__init__(command_line)
        self._close_lock = threading.Lock()
        self._closing = threading.Event()
        self._terminate_sent = False

    @property
    def closed(self):
        return self.process.poll() is not None

    def close(self):
        self._closing.set()

        with self._close_lock:
            if self.process.poll() is not None:
                return

            if self._terminate_sent:
                return

            try:
                self.process.terminate()
            except ProcessLookupError:
                pass
            else:
                self._terminate_sent = True

    def recv(self, size):
        """Read proxy output, treating subprocess EOF as socket EOF.

        Paramiko's ProxyCommand.recv() continues looping when os.read()
        returns b'' at subprocess EOF. During shutdown that leaves the
        Transport thread inside recv() until another thread closes stdout,
        at which point stdout.fileno() raises ValueError and Paramiko logs an
        "Unknown exception" traceback. A socket-style recv must return b''
        at EOF instead.
        """
        buffer = b""
        start = time.time()

        try:
            while len(buffer) < size:
                select_timeout = None

                if self.timeout is not None:
                    elapsed = time.time() - start
                    if elapsed >= self.timeout:
                        raise socket.timeout()
                    select_timeout = self.timeout - elapsed

                readable, _, _ = select(
                    [self.process.stdout],
                    [],
                    [],
                    select_timeout,
                )

                if readable:
                    chunk = os.read(
                        self.process.stdout.fileno(),
                        size - len(buffer),
                    )

                    if not chunk:
                        return buffer

                    buffer += chunk

            return buffer

        except socket.timeout:
            if buffer:
                return buffer
            raise
        except ValueError:
            stdout = getattr(self.process, 'stdout', None)
            process_stopped = self.process.poll() is not None

            if (
                self._closing.is_set()
                or process_stopped
                or stdout is None
                or stdout.closed
            ):
                return buffer

            raise
        except OSError as exc:
            if self._closing.is_set() or self.process.poll() is not None:
                return buffer

            raise paramiko.ProxyCommandFailure(
                " ".join(self.cmd),
                exc.strerror or str(exc),
            )

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
            #if self.channel.interaction_thread:
            #    self.channel.interaction_loop.call_soon_threadsafe(self.channel.interaction_loop.stop) 
            #    self.channel.interaction_thread.join()

            ## close event loop
            #event_loop = self.channel.owner.event_loop
            #tasks = asyncio.all_tasks(event_loop)
            #if tasks:          
            #    for task in tasks:
            #        task.cancel()
            #    event_loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            #if event_loop.is_running():
            #    event_loop.call_soon_threadsafe(event_loop.stop) 
            self.channel.owner.call_thread.join()
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

    #@export2Dollar
    #def close_session(self):
    #    return self.close()

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

        if self._thread_appened_to is None: return None
        result = self._thread_appened_to.sshscriptstack.pop(self)
        self._thread_appened_to = None
        return result        
        

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
        logger.debug('Script requested break (exit_code=%s)', code)
        raise SSHScriptBreak(message,code)

    @export2Dollar
    def exit(self,code=0,message=''):
        logger.debug('Script requested exit (exit_code=%s)', code)
        raise SSHScriptExit(message,code)

    @export2Dollar
    def connect(self,host,username=None,password=None,port=22,policy=None,**kw):
        """
        create a sub Session() and call SSHClient.connect() to connect to remote host.
        the connection has a default keep alive interval of 60 seconds, for customizing, please
        set os.environ['KEEPALIVE_INTERVAL'] to your favorite value. value '0' would disable this setting.
        
        host:
            when host is in format of "username@host", then the second parameter would set to password, 
            which means user can call this function like below:
                $.connect('user@host',password) instead of $.connect('user@host',password=password)
        policy:
            args for paramiko's SSHClient.set_missing_host_key_policy()
            when policy is None, its default is AutoAddPolicy
        kw:dict
            kw['proxyCommand']: 
                setting proxyCommand. If presented, the next arguments were set:
                    kw['banner_timeout'] = 200000
                    kw['timeout'] = 200000
                    kw['auth_timeout' ] = 200000
            kw['pkey_path']: 
                the path to get private key. The value was set to 'pkey' for SSHClient.connect()

            other args which should directly pass into paramiko's SSHClient.connect()
        Return:
            An instance of Session(), the connected subsession. 
        Throws:
            paramiko's exceptions of SSHClient.connect() 
        """
        
        if self.closed:
            raise RuntimeError('cannot connect from a closed session')        
        
        ## host might be in format of "username@hostname"
        if '@' in host:
            if username and password is None:
                password = username
            username,host = host.split('@')

        has_proxy = 'proxyCommand' in kw
        is_nested = self._client is not None
        logger.debug(
            'Opening SSH connection (host=%s, port=%s, username=%s, nested=%s, proxy=%s)',
            host,
            port,
            username,
            is_nested,
            has_proxy,
        )

        def connect_client(host,username,password,port,policy,**kw):
            client = paramiko.SSHClient()
            try:
                ## client.load_system_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
                if policy: client.set_missing_host_key_policy(policy)
                client.connect(host,username=username,password=password,port=port,**kw)
                return client
            except BaseException:
                try:
                    client.close()
                except BaseException as cleanup_exc:
                    logger.warning(
                        'Unable to close SSH client after connection failure '
                        '(host=%s, exception_type=%s)',
                        host,
                        type(cleanup_exc).__name__,
                    )                
                raise
        ## user can set policy=0 to disable client.set_missing_host_key_policy
        if policy is None:
            ## allow connect to host not which is in known_hosts
            policy = paramiko.AutoAddPolicy()

        ## convert pkey_path to pkey, if "pkey" has existed, would raise ValueError
        if 'pkey_path' in kw:
            if 'pkey' in kw: raise ValueError(f'"pkey_path" was given when "pkey" has existed')
            kw['pkey'] = self.pkey(kw['pkey_path'])
            del kw['pkey_path']

        if is_nested and has_proxy:
            raise NotImplementedError(
                'proxyCommand is not supported in a nested session'
            )

        ## If this session already has a connection, create a child Session
        ## which uses it as the parent for the nested connection.
        subsession = Session(self)
        subsession._host = host
        subsession._port = port
        subsession._username = username
        try:
            if is_nested:
                ## a nested connection
                logger.debug(
                    'Opening nested SSH transport (host=%s, port=%s, username=%s)',
                    host,
                    port,
                    username,
                )
                ## REF: https://stackoverflow.com/questions/35304525/nested-ssh-using-python-paramiko
                dest_addr = (host,port)
                local_addr = (self.host,self.port)
                subsession._sock = self._client.get_transport().open_channel("direct-tcpip", dest_addr, local_addr)
                subsession._client = connect_client(host,username,password,port,policy,sock=subsession._sock,**kw)
            elif has_proxy:
                logger.debug(
                    'Opening SSH connection through proxy command '
                    '(host=%s, port=%s, username=%s)',
                    host,
                    port,
                    username,
                )
                subsession._sock = subsession._socket_of_proxy_command(kw['proxyCommand'])
                del kw['proxyCommand']
                kw.setdefault('banner_timeout', 30)
                kw.setdefault('timeout', 30)
                kw.setdefault('auth_timeout', 30)                
                subsession._client = connect_client(host,username,password,port,policy,sock=subsession._sock,**kw)
            else:
                logger.debug(
                    'Opening direct SSH transport (host=%s, port=%s, username=%s)',
                    host,
                    port,
                    username,
                )
                subsession._client = connect_client(host,username,password,port,policy,**kw)
            ## keep alive (added from v1.1.18)
            keepAliveInterval = int(os.environ.get('KEEPALIVE_INTERVAL','60'))
            if keepAliveInterval > 0:
                subsession._client.get_transport().set_keepalive(
                    keepAliveInterval
                )
                    
            logger.debug(
                'Configured SSH keepalive (host=%s, interval_seconds=%s)',
                host,
                keepAliveInterval,
            )
            logger.info(
                'SSH connection opened (host=%s, port=%s, username=%s, nested=%s, proxy=%s)',
                host,
                port,
                username,
                is_nested,
                has_proxy,
            )
            # 所有步驟成功後，正式交給 parent 管理。
            self.subsessions.append(subsession)
            return subsession
        except BaseException:
            try:
                subsession.close()
            except BaseException as cleanup_exc:
                logger.warning(
                    'Unable to clean up failed SSH connection '
                    '(host=%s, exception_type=%s)',
                    host,
                    type(cleanup_exc).__name__,
                )
            raise

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
        
       
        logger.info(
            'Starting upload (host=%s, source=%s, destination=%s)',
            self.host,
            src,
            os.path.join(remoteCwd,dst),
        )
        
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
                return foldersToMake

            ## check un-existing folder(from down to top; suppose last one is a file)
            foldersToMake = checking(dst,[])
            if len(foldersToMake):
                foldersToMake.reverse()
                for folder in foldersToMake:
                    logger.debug(
                        'Creating remote upload directory (host=%s, path=%s)',
                        self.host,
                        folder,
                    )
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
        logger.info(
            'Upload completed (host=%s, source=%s, destination=%s)',
            self.host,
            src,
            dst,
        )
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

        logger.info(
            'Starting download (host=%s, source=%s, destination=%s)',
            self.host,
            src,
            dst,
        )
        
        self.sftp.get(src,dst)
        
        logger.info(
            'Download completed (host=%s, source=%s, destination=%s)',
            self.host,
            src,
            dst,
        )
        return (src,dst)

    def _socket_of_proxy_command(self, argsOfProxyCommand):
        return _IdempotentProxyCommand(argsOfProxyCommand)

    def run(self,script,vars=None,showScript=False):
        if vars is None:
            vars = sys._getframe(1).f_locals
        return self.run_in_eventloop(script,vars,showScript)

    def run_in_eventloop(self,script,vars=None,showScript=False):
        
        def executeScript(script,_vars,showScript=False):
            filepath = _vars.get('__file__')
            ## v2.0 auto detecting script types
            is_dollar_script = False
            try:
                ## testing if this is a regular python script
                ast.parse(script)
            except SyntaxError:
                is_dollar_script = True
            
            if showScript:
                scriptChunk = (
                    dollarparser.convert(filepath or '<str>', script)
                    if is_dollar_script else script
                )
                dumpScript(scriptChunk)
                return {}


            source_path = filepath or '<str>'
            

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
            exec_vars['sys']= sys
            exec_vars['types']= types
            exec_vars['Dollar'] = Dollar

            if is_dollar_script:
                code = dollarparser.compile_spy(source_path, script)
            else:
                dollarparser._cache_source(source_path, script)
                code = compile(script, source_path, 'exec')
            try:
                exec(code, exec_vars)  # Run the modified code inside the module's namespace
            except SSHScriptBreak:
                ## ignore this exception
                return exec_vars
            except SSHScriptExit as e:
                ## v2.0.3, same as SSHScriptExit
                raise SystemExit(e.errno)
            else:
                return exec_vars
            
        ## v.1.18
        if not self.runLocker.acquire(timeout=60):
            raise TimeoutError('Timed out waiting for the script execution lock')
        
        
        def runner(*args):
            runSession = f"{self.host}:{threading.current_thread().native_id}"
            started_at = time.monotonic()
            outcome = 'completed'
            exit_code = None
            exception_type = None
            ret = {}
            try:
                ret['value'] = executeScript(*args)
            except SystemExit as e:
                ret['system_exit'] = e
                outcome = 'system_exit'
                exit_code = e.code
            except SSHScriptException as e:
                ret['exception'] = e
                ret['exitcode'] = e.errno
                outcome = 'sshscript_error'
                exit_code = e.errno
                exception_type = type(e).__name__
            except Exception as e:
                ret['exception'] = e
                outcome = 'error'
                exception_type = type(e).__name__
            finally:
                logger.debug(
                    'Script execution finished '
                    '(session=%s, outcome=%s, exit_code=%s, exception_type=%s, duration_ms=%d)',
                    runSession,
                    outcome,
                    exit_code,
                    exception_type,
                    int((time.monotonic() - started_at) * 1000),
                )
            return ret

        try:
            ret = runner(script,vars,showScript)
        finally:
            ## self.runLocker might be already released by caller because of timeout
            if self.runLocker.locked():
                self.runLocker.release()
        
        if ret.get('exception'):
            raise ret['exception']
        elif ret.get('system_exit'):
            sys.exit(ret['system_exit'].code)
        else:
            ## what is for, for next spy script?
            ret['value']['_sshscriptstacks_'] = threading.current_thread().sshscriptstack
            return ret['value']

    ## v2.0.3 added feature
    @export2Dollar
    def clear(self):
        if self._lastDollar: self._lastDollar.clear()


    def exec_command(self,cmd:str,*,shell=None,shell_executable=None,
                     _legacy_twodollars=False,**kw):
        """Execute one command, automatically selecting direct or shell mode.

        ``shell=None`` (the default) performs quote-aware command inspection.
        ``shell=False`` forces direct execution and ``shell=True``
        forces POSIX shell execution.  ``shell='bash'`` selects and enables a
        named shell.
        """
        if not isinstance(cmd,str):
            raise TypeError(f'command must be str, not {type(cmd).__name__}')
        cmd = cmd.strip()
        if not cmd:
            raise ValueError('command must not be empty')

        if isinstance(shell,str):
            if shell_executable is not None:
                raise ValueError('use either shell="name" or shell_executable, not both')
            shell_executable = shell
            shell = True
        elif shell is not None and not isinstance(shell,bool):
            raise TypeError('shell must be None, bool, or a shell executable name')

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

    ## delegates to self._lastDollar
    ## eg. 1st level $.wait
    @property
    def dollar(self):
        return self._lastDollar
    @property
    def stdout(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.stdout

    @property
    def stderr(self):
        if self._lastDollar is None: raise ValueError('no execution result yet')
        return self._lastDollar.stderr

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

        cleanup_errors = []
        transport = None
        
        for subsession in reversed(tuple(self.subsessions)):
            subsession.close()

        if self._client is not None:

            try:
                transport = self._client.get_transport()
            except Exception as exc:
                cleanup_errors.append(('get SSH transport', exc))

            if self._sftp:
                self._sftp.close()
                self._sftp = None

            logger.info(
                'Closing SSH connection (host=%s, port=%s, username=%s)',
                self.host,
                self.port,
                self.username,
            )
            try:
                self._client.close()
            except Exception as exc:
                logger.debug(
                    'Unable to close SSH client cleanly '
                    '(host=%s, exception_type=%s)',
                    self.host,
                    type(exc).__name__,
                )
            finally:
                self._client = None

        ## don't acquire self.runLocker, since this might be called by self.run()
        ##self.runLocker.acquire(timeout=60)
                 
        ## close the socket of proxyCommand, if any
        if self._sock is not None:
            try:
                if isinstance(self._sock,paramiko.proxy.ProxyCommand):
                    complete, forced_kill, errors = (
                        self._cleanup_proxy_command(
                            self._sock,
                            transport=transport,
                        )
                    )
                    cleanup_errors.extend(errors)

                    if forced_kill:
                        logger.warning(
                            'Proxy command required forced termination '
                            '(host=%s, pid=%s)',
                            self.host,
                            self._sock.process.pid,
                        )

                    if complete:
                        self._sock = None                    
                else:
                    try:
                        self._sock.close()
                    except Exception as exc:
                        cleanup_errors.append(('close SSH socket', exc))
                    else:
                        self._sock = None                
            except Exception as exc:
                logger.debug(
                    'Unable to close SSH socket cleanly '
                    '(host=%s, exception_type=%s)',
                    self.host,
                    type(exc).__name__,
                )
            finally:
                self._sock = None


        if self.host is not None:
            logger.debug(
                'SSH connection closed (host=%s, port=%s, username=%s)',
                self.host,
                self.port,
                self.username,
            )
        
        self._host = None
        self._port = None
        self._username = None

        self.closed = True

        ## remove self from parent session        
        if self.parent:
            try:
                self.parent.subsessions.remove(self)
            except ValueError:
                logger.debug(
                    'Session is not registered with its parent '
                    '(session=%s, parent=%s)',
                    self,
                    self.parent,
                )
            else:
                logger.debug(
                    'Removed session from its parent session (session=%s, parent=%s)',
                    self,
                    self.parent,
                )
        ## auto unbind to current thread
        self._pop_from_thread_stack()

    ## alias
    disconnect = close    
    def __del__(self):
        self.close()

    def _cleanup_proxy_command(self, proxy, transport=None):
        process = proxy.process
        errors = []
        forced_kill = False

        # 若 SSHClient.close() 沒有碰到 supplied socket，
        # 這裡補送一次 SIGTERM。
        try:
            proxy.close()
        except ProcessLookupError:
            pass
        except Exception as exc:
            errors.append(('terminate proxy', exc))

        try:
            process.wait(timeout=_PROXY_TERMINATE_TIMEOUT)

        except subprocess.TimeoutExpired:
            forced_kill = True

            try:
                process.kill()
            except ProcessLookupError:
                pass
            except BaseException as exc:
                errors.append(('kill proxy', exc))

            try:
                # kill 後仍然必須 wait，否則可能留下 zombie。
                process.wait(timeout=_PROXY_KILL_TIMEOUT)
            except subprocess.TimeoutExpired as exc:
                errors.append((
                    'wait for proxy after kill',
                    TimeoutError(
                        'proxy process did not exit after terminate and kill '
                        f'(pid={process.pid})'
                    ),
                ))
            except BaseException as exc:
                errors.append(('wait for proxy after kill', exc))

        except BaseException as exc:
            errors.append(('wait for proxy after terminate', exc))

        transport_stopped = True

        if (
            transport is not None
            and transport is not threading.current_thread()
        ):
            try:
                if transport.is_alive():
                    transport.join(_TRANSPORT_JOIN_TIMEOUT)
                transport_stopped = not transport.is_alive()
            except BaseException as exc:
                errors.append(('wait for SSH transport', exc))
                transport_stopped = False

        # 每個 pipe 必須獨立關閉。
        for stream_name in ('stdin', 'stdout', 'stderr'):
            stream = getattr(process, stream_name, None)

            if stream is None or stream.closed:
                continue

            try:
                stream.close()
            except BaseException as exc:
                errors.append((f'close proxy {stream_name}', exc))

        # A third-party ProxyCommand implementation may not return b'' at
        # subprocess EOF. Closing its pipes above is the final wake-up; give
        # the Transport one bounded chance to finish before Session.close()
        # returns.
        if (
            not transport_stopped
            and transport is not None
            and transport is not threading.current_thread()
        ):
            try:
                transport.join(_TRANSPORT_JOIN_TIMEOUT)
                transport_stopped = not transport.is_alive()
            except BaseException as exc:
                errors.append(('wait for SSH transport after pipe close', exc))

        if not transport_stopped:
            errors.append((
                'wait for SSH transport',
                TimeoutError(
                    'SSH transport thread did not stop during proxy cleanup'
                ),
            ))

        try:
            reaped = process.poll() is not None
        except BaseException as exc:
            errors.append(('poll proxy', exc))
            reaped = False

        streams_closed = all(
            stream is None or stream.closed
            for stream in (
                getattr(process, 'stdin', None),
                getattr(process, 'stdout', None),
                getattr(process, 'stderr', None),
            )
        )

        return (
            reaped and streams_closed and transport_stopped,
            forced_kill,
            errors,
        )
