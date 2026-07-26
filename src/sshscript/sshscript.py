#!/usr/bin/env python3
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
import os
import sys
import glob
import __main__
import traceback

# set here used in sshscriptdollar
import warnings
def warning_on_one_line(message, category, filename, lineno, file=None, line=None):
    return '%s:%s: %s: %s\n' % (filename, lineno, category.__name__, message)
warnings.formatwarning = warning_on_one_line

try:
    from .session import Session
    from .errorutils import SSHScriptExit, SSHScriptBreak,  get_logger, log_debug, log_debug_8,SSHScriptException
    ## 2025/3/3 v2.0.3 feature: import *.spy file directly
    from . import spyimporter
    from . import __init__ as sshscript_module
except ImportError:
    ## 2024/8/16, should add mydir into sys.path for python 3.12
    mydir = os.path.abspath(os.path.dirname(__file__))
    if not mydir in sys.path: sys.path.insert(0,mydir)
    from session import Session
    from errorutils import SSHScriptExit, SSHScriptBreak, get_logger, log_debug, log_debug_8, SSHScriptException
    import spyimporter
    import __init__ as sshscript_module
    ## 2024/8/16, should remove mydir out of sys.path for python 3.11
    if mydir == sys.path[0]: del sys.path[0]

## initial logger
logger = get_logger()

def run_file(givenPaths,
        vars=None,
        showScript=False,
        showRunOrder=False,
        unisession=True)->int:
    ## @unisession:bool, if true, use the same session(an instance of Session) for all files.
    if isinstance(givenPaths, str): givenPaths = [givenPaths]

    paths = []
    ext = '.spy'
    for path in givenPaths:
        abspath = os.path.abspath(path)
        ## if path is a directory, add all *.spy files in it
        if os.path.isdir(abspath):
            # files in folder are sorted by name
            unsortedFilesInPath = list(filter(lambda x: x[-4:] == ext,[os.path.abspath(os.path.join(path,y)) for y in os.listdir(path)]))
        else:
            ## glob.glob returns a list of files, or empty list if no file matches
            unsortedFilesInPath = list(filter(lambda x: os.path.splitext(x)[1] == ext ,glob.glob(abspath)))
            if len(unsortedFilesInPath) == 0:
                if not os.path.exists(abspath):
                    ## In context of sshscript, this may be a argument to the script.
                    ## If the script also wants to accept command line arguments,
                    ## it should assign the argument in form of
                    ## --arg=value , not in form of --arg value
                    ## otherwise, this exception would raised
                    raise RuntimeError(f'{os.path.abspath(path)} not found')
                elif os.path.isfile(abspath):
                    unsortedFilesInPath.append(abspath)
                else:
                    raise RuntimeError(f'{abspath} not supported')
        
        unsortedFilesInPath.sort()
        for p in unsortedFilesInPath:
            ## ignoring duplicate path
            if p in paths: continue
            paths.append(p)

    if showRunOrder:
        for path in paths: print(path)
        return 0
    
    ## starts the executions of every script
    _vars = locals().copy()
    if vars: _vars.update(vars)
    #_globals = globals().copy()

    if unisession:
        session = Session()
    else:
        session = None
    exitcode = 0
    for idx,file in enumerate(paths):
        ## when unisession is not True,
        ## generate a new session for every file
        if not unisession: session = Session()

        log_debug(f'executing {file}')

        absfile = os.path.abspath(file)
        ## maybe strange, but probably also works on windows
        with open(absfile,'rb') as fd:
            script = fd.read().decode('utf-8','replace')

        ## add folder to sys.path,so "import <module in the same folder of __file__>" works
        scriptFolder = os.path.dirname(absfile)
        scriptFolderInsertedToSysPath = False
        if not scriptFolder in sys.path:
            scriptFolderInsertedToSysPath = True
            sys.path.insert(0,scriptFolder)

        try:
            _vars['__name__'] = '__main__' if idx == 0 else os.path.basename(absfile)
            _vars['__file__'] = absfile
            _vars['sshscript'] = sshscript_module
            ## parse the file only if it is .spy
            ## v2.0.3 changes the order from locals,globals to globals,locals
            newvars = session.run(script,_vars,showScript=showScript)
        except SSHScriptException as e:
            exitcode = e.errno
            raise
        except SSHScriptBreak as e:
            log_debug_8(f'break by {e}')
            exitcode = e.errno
            continue
        except SSHScriptExit as e:
            log_debug_8(f'exit by {e}')
            exitcode = e.errno
            raise
        except Exception as e:
            log_debug_8(f'exit by {e}')
            raise
        else:
            exported = newvars.get('__export__')        
            if exported:
                ## __export__ = '*' will export all
                if '*' == exported:
                    _vars.update(newvars)
                else:
                    basename = os.path.basename(file)
                    for key in exported:
                        log_debug_8(f'{basename} export {key}')
                        _vars[key] = newvars[key]
            _vars['_sshscriptstacks_'] = newvars['_sshscriptstacks_']
        finally:
            ## restore sys.path
            if scriptFolderInsertedToSysPath:
                sys.path.remove(scriptFolder)
            if not unisession:    
                session.close()
                del session

    if unisession:    
        session.close()
        del session
    
    return exitcode


def run_script(script,varGlobals=None,showScript=False):
    session = Session()
    try:
        ## this is a blocking call
        return session.run(script,vars=varGlobals,showScript=showScript)
    finally:
        session.close()

def main():
    import argparse

    # REF: https://stackoverflow.com/questions/15753701/how-can-i-pass-a-list-as-a-command-line-argument-with-argparse
    parser = argparse.ArgumentParser(description='SSHScript: automation tools for Subprocess and SSH')

    ## v2.0.3, only one .spy file is allowed, this makes no sense
    #parser.add_argument('--run-order', dest='showRunOrder', action='store_true',
    #                    default=False,
    #                    help='show the files to run in order, no execution.')

    parser.add_argument('--script','-s', dest='showScript', action='store_true',
                        default=False,
                        help='show the converted python script only, no execution.')
    
    parser.add_argument('--verbose','-v', dest='verbose', action='store_true',
                        default=False,
                        help='dump stdout,stderr to console.')   

    parser.add_argument('--stderr', dest='verbose_stderr', action='store_true',
                        default=False,
                        help='dump stderr only to console.')   


    parser.add_argument('path', action='store', nargs='?',default='_',
                        help='path of .spy files or folders')

    parser.add_argument('--debug','-d', dest='debug', nargs='*',
                        help='debug level: 8 or 10, default is 10')


    ## new on v1.1.17
    parser.add_argument('--version', dest='version', action='store_true',default=False,
                        help='dump the version number')

    ## new on v2.0.2
    parser.add_argument('--check', dest='checkversion', action='store_true',default=False,
                        help='check the last version of SSHScript (need internet)')

    args, unknown = parser.parse_known_args()
   
    ## add unknown arguments to sys.argv
    del sys.argv[1:] 
    sys.argv.extend(unknown)

    def get_current_version():
        try:
            from __init__ import __version__
        except ImportError:
            try:
                from . import __version__
            except ImportError:
                __version__ = 'unknown'
        return __version__

    ## handle the contradiction between args.debug and args.paths
    if args.path == '_':
        if args.debug and len(args.debug) == 1:
            ## sshscript.py  --debug unittest-v2.0.3/A01onedollar.spy 
            args.path = args.debug[0]
            args.debug = 10
        elif args.debug and len(args.debug) > 1:
            ## sshscript.py  --debug 8  unittest-v2.0.3/A01onedollar.spy 
            args.path = args.debug[1]
            args.debug = int(args.debug[0])
        else:
            args.path = None
    elif args.debug is not None:
        if len(args.debug) == 0:
            ## sshscript.py unittest-v2.0.3/A01onedollar.spy --debug
            args.debug = 10
        elif len(args.debug) > 0:
            ## sshscript.py unittest-v2.0.3/A01onedollar.spy --debug 8
            args.debug = int(args.debug[0])
    ## handling starts
    if (args.version):
        print(get_current_version())
    elif (args.checkversion):
        __version__ = get_current_version()
        import urllib.request
        import json
        info = json.loads(urllib.request.urlopen("https://iapyeh.github.io/sshscript/info.json",timeout=3).read())
        mime = [x for x in __version__.split('.')]
        current = [x for x in info['version'].split('.')]
        print(f'The latest release of SSHScript is {info["version"]}, you have version {__version__} installed.')
        if not __version__ == info['version']:
            canupgrade = True
            for i in range(3):
                if mime[i] > current[i]:
                    canupgrade = False
                    break
            if canupgrade:
                print(f"Installed SSHScript Version is \"{__version__}\", SSHScript has new version \"{info['version']}\".")
                print("  You can upgrade it by: (choose one)")
                print(f"  1.  pip install sshscript --upgrade")
                print(f"  2.  pip install sshscript=={info['version']} --upgrade")
                print(f"  3.  {sys.executable} -m pip install sshscript --upgrade")
                print(f"  4.  {sys.executable} -m pip install sshscript=={info['version']} --upgrade")

    elif args.path:
        
        sys.argv[0] = args.path

        if args.debug:
            os.environ['DEBUG'] = str(args.debug)
            logger.reset_debug()
        
        if args.verbose:
            os.environ['VERBOSE'] = '1'
        elif args.verbose_stderr:
            os.environ['VERBOSE_STDERR'] = '1'

        ## v3, only one .spy file is allowed, this makes no sense
        #if args.folder:
        #    paths = [os.path.join(args.folder,x) for x in args.paths]
        #else:
        #    paths = args.paths

        try:
            run_file([args.path],
                showScript=args.showScript,
                showRunOrder=False,
                unisession=True)
        except SSHScriptExit as e:
            sys.exit(e.errno)
        except SSHScriptException as e:
            sys.exit(e.errno)
        except Exception as e:
            traceback.print_exc()
            sys.exit(1)
        else:
            sys.exit(0)
    elif sys.stdout.isatty():
        # check new version, new from 1.1.13
        try:
            from __init__ import __version__
        except ImportError:
            try:
                from . import __version__
            except ImportError:
                __version__ = None
        
        if __version__: print(f'Version:{__version__}')
        
        parser.print_help()
    
if __name__ == '__main__':
    main()
