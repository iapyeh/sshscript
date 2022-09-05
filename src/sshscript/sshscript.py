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
from paramiko.common import (
    DEBUG,
)
import os, sys,glob
import __main__

# set here used in sshscriptdollar
import warnings
def warning_on_one_line(message, category, filename, lineno, file=None, line=None):
    return '%s:%s: %s: %s\n' % (filename, lineno, category.__name__, message)
warnings.formatwarning = warning_on_one_line

try:
    from .sshscriptcore import SSHScript
    from .sshscripterror import SSHScriptExit, SSHScriptBreak, SSHScriptCareful, setupLogger
except ImportError:
    from sshscriptcore import SSHScript
    from sshscripterror import SSHScriptExit, SSHScriptBreak, SSHScriptCareful, setupLogger


def runFile(givenPaths,
        varGlobals=None,
        varLocals=None,
        showScript=False,
        showRunOrder=False,
        unisession=True):
    """
    @unisession:bool, if true, use the same session(an instance of SSHScript) 
                for all files.
    """
    
    if isinstance(givenPaths, str): givenPaths = [givenPaths]
    
    ext = os.environ.get('SSHSCRIPT_EXT','.spy')

    paths = []
    for path in givenPaths:
        abspath = os.path.abspath(path)
        # if path is a directory, add all *.spy files in it
        if os.path.isdir(abspath):
            # files in folder are sorted by name
            unsortedFilesInPath = list(filter(lambda x: x[-4:] == ext,[os.path.abspath(os.path.join(path,y)) for y in os.listdir(path)]))
        else:
            # glob.glob returns a list of files, or empty list if no file matches
            unsortedFilesInPath = list(filter(lambda x: os.path.splitext(x)[1] == ext ,glob.glob(abspath)))
            if len(unsortedFilesInPath) == 0:
                if not os.path.exists(abspath):
                    # In context of sshscript, this may be a argument to the script.
                    # If the script also wants to accept command line arguments,
                    # it should assign the argument in form of
                    # --arg=value , not in form of --arg value
                    # otherwise, this exception would raised
                    raise RuntimeError(f'{os.path.abspath(path)} not found')
                elif os.path.isfile(abspath):
                    unsortedFilesInPath.append(abspath)
                else:
                    raise RuntimeError(f'{abspath} not supported')
        
        unsortedFilesInPath.sort()
        for p in unsortedFilesInPath:
            if p in paths:
                print('ignoring duplicate path: %s' % p)
                continue
            paths.append(p)

    if showRunOrder:
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
    exitcode = 0
    for file in paths:
        # 每一個檔案產生一個sshscript物件
        if not unisession:
            session = SSHScript()

        session.log(DEBUG,f'run {file}')

        
        absfile = os.path.abspath(file)
        # 有點怪，但比較能windows時也適用
        with open(absfile,'rb') as fd:
            script = fd.read().decode('utf-8')

        # add folder to sys.path,so "import <module in the same folder of __file__>" works
        scriptFolder = os.path.dirname(abspath)
        scriptFolderInsertedToSysPath = False
        if not scriptFolder in sys.path:
            scriptFolderInsertedToSysPath = True
            sys.path.insert(0,scriptFolder)

        try:
            _locals['__file__'] = absfile
            newglobals = session.run(script,_locals.copy(),_globals.copy(),showScript=showScript)
        except SSHScriptBreak as e:
            session.log(DEBUG,f'break by {e}')
            exitcode = e.code
            continue
        except SSHScriptExit as e:
            session.log(DEBUG,f'exit by {e}')
            exitcode = e.code
            raise
        except Exception as e:
            session.log(DEBUG,f'exit by {e}')
            raise
        else:
            # restore sys.path
            if scriptFolderInsertedToSysPath:
                sys.path.remove(scriptFolder)

            exported = newglobals.get('__export__')        
            if exported:
                # __export__ = '*' will export all
                if '*' == exported:
                    #_locals.update(newlocals)
                    _globals.update(newglobals)
                else:
                    basename = os.path.basename(file)
                    for key in exported:
                        session.log(DEBUG,f'{basename} export {key}')
                        #_locals[key] = newlocals[key]
                        _globals[key] = newglobals[key]
        finally:
            if not unisession:    
                session.close()
                del session

    if unisession:    
        session.close()
        del session
    
    return exitcode

def runScript(script,varGlobals=None,varLocals=None):
    session = SSHScript()
    session.run(script,varGlobals,varLocals,showScript=False)
    session.close()

   

def main():
    import argparse

    # REF: https://stackoverflow.com/questions/15753701/how-can-i-pass-a-list-as-a-command-line-argument-with-argparse
    parser = argparse.ArgumentParser(description='SSHScript')

    parser.add_argument('--run-order', dest='showRunOrder', action='store_true',
                        default=False,
                        help='show the files to run in order, no execution.')

    parser.add_argument('--script', dest='showScript', action='store_true',
                        default=False,
                        help='show the converted python script only, no execution.')
    
    parser.add_argument('--verbose', dest='verbose', action='store_true',
                        default=False,
                        help='dump stdout,stderr to console. "debug" implies "verbose".')   

    parser.add_argument('--ext', dest='sshscriptExt', action='store',
                        default='.spy',
                        help='the extension of sshscript file. default is .spy')

    parser.add_argument('--debug', dest='debug', action='store_true',
                        default=False,
                        help='set log level to debug')

    parser.add_argument(dest='paths', action='store', nargs='*',
                        help='path of .spy files or folders')

    # new on v1.1.13
    parser.add_argument('--folder', dest='folder', action='store',default='',
                        help='base folder of paths')

    args, unknown = parser.parse_known_args()
    __main__.unknown_args = unknown

    os.environ['SSHSCRIPT_EXT'] = args.sshscriptExt

    if len(args.paths):
        
        if args.debug:
            os.environ['DEBUG'] = '1'
        
        if args.verbose:
            os.environ['VERBOSE'] = '1'

        setupLogger()

        if args.folder:
            paths = [os.path.join(args.folder,x) for x in args.paths]
        else:
            paths = args.paths
        try:
            runFile(paths,
                varGlobals=None,
                varLocals=None,
                showScript=args.showScript,
                showRunOrder=args.showRunOrder,
                unisession=True)
        except SSHScriptExit as e:
            sys.exit(e.code)
        except Exception as e:
            import traceback
            traceback.print_exc()
            code = e.code if hasattr(e,'code') else 1
            sys.exit(code)
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
                __version__ = 'unknown'

        print()
        parser.print_help()

        def checkversion():
            try:
                import urllib.request
                import json
                info = json.loads(urllib.request.urlopen("https://iapyeh.github.io/sshscript/info.json",timeout=3).read())
                mime = [x for x in __version__.split('.')]
                current = [x for x in info['version'].split('.')]
                if __version__ == info['version']:
                    print(f'Installed SSHScript version "{__version__}" is the most updated version.')
                else:
                    canupgrade = False
                    for m,c in zip(mime,current):
                        if int(m) < int(c):
                            canupgrade = True
                            break
                    if canupgrade:
                        print(f"Installed SSHScript Version is \"{__version__}\", SSHScript has new version \"{info['version']}\".")
                        print("  You can upgrade it by: (choose one)")
                        print(f"  1.  pip install sshscript --upgrade")
                        print(f"  2.  pip install sshscript=={info['version']} --upgrade")
                        print(f"  3.  {sys.executable} -m pip install sshscript --upgrade")
                        print(f"  4.  {sys.executable} -m pip install sshscript=={info['version']} --upgrade")
                    else:
                        print(f"Installed SSHScript Version is \"{__version__}\"(official release is \"{info['version']}\").")

            except:
                print(f'SSHScript Version:{__version__}')
        
        import threading
        threading.Thread(target=checkversion).start()
        
    

# SSHScriptDollar need this value to work 
# when sshscript is imported as a module (main() not been called)
__main__.SSHScript = SSHScript

if __name__ == '__main__':
    main()