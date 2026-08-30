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
import time
import traceback
## starts from 3.1, asyncio is introduced.
__version__ = "3.1.0"

# set here used in sshscriptdollar
import warnings
def warning_on_one_line(message, category, filename, lineno, file=None, line=None):
    return '%s:%s: %s: %s\n' % (filename, lineno, category.__name__, message)
warnings.formatwarning = warning_on_one_line

if __package__:
    from .session import Session
    from .errorutils import SSHScriptExit, SSHScriptBreak, get_logger, set_logger, SSHScriptException,command_summary
    ## 2025/3/3 v2.0.3 feature: import *.spy file directly
    from . import spyimporter
else:
    ## 2024/8/16, should add mydir into sys.path for python 3.12
    mydir = os.path.abspath(os.path.dirname(__file__))
    if not mydir in sys.path: sys.path.insert(0,mydir)
    from session import Session
    from errorutils import SSHScriptExit, SSHScriptBreak, get_logger, set_logger, SSHScriptException,command_summary
    import spyimporter
    ## 2024/8/16, should remove mydir out of sys.path for python 3.11
    if mydir == sys.path[0]: del sys.path[0]

## run_file() exposes this public module object to executed .spy scripts.
## Referencing sys.modules avoids importing __init__.py back from this module.
sshscript_module = sys.modules[__package__ or __name__]

## initial logger
logger = get_logger()

def run_file(script_path,
        vars=None,
        showScript=False)->int:
    ## starts from v3.1, this routine runs one file only.
   
    ## starts the executions of every script
    _vars = locals().copy()
    if vars: _vars.update(vars)
    #_globals = globals().copy()

    the_session = Session()
    exitcode = 0
    absfile = os.path.abspath(script_path)
    started_at = time.monotonic()
    outcome = 'failed'
    script_exitcode = None
    exception_type = None
    logger.debug('Starting script file (path=%s)', absfile)

    scriptFolder = os.path.dirname(absfile)
    scriptFolderInsertedToSysPath = False
    try:
        ## maybe strange, but probably also works on windows
        with open(absfile,'rb') as fd:
            script = fd.read().decode('utf-8','replace')

        ## add folder to sys.path,so "import <module in the same folder of __file__>" works
        if not scriptFolder in sys.path:
            scriptFolderInsertedToSysPath = True
            sys.path.insert(0,scriptFolder)

        _vars['__name__'] = '__main__'
        _vars['__file__'] = absfile
        _vars['sshscript'] = sshscript_module
        ## parse the file only if it is .spy
        ## v2.0.3 changes the order from locals,globals to globals,locals
        newvars = the_session.run(script,_vars,showScript=showScript)
    except SSHScriptBreak as e:
        exitcode = e.errno
        script_exitcode = e.errno
        outcome = 'break'
    except SSHScriptExit as e:
        exitcode = e.errno
        script_exitcode = e.errno
        outcome = 'exit'
        raise
    except SSHScriptException as e:
        exitcode = e.errno
        script_exitcode = e.errno
        outcome = 'sshscript_error'
        exception_type = type(e).__name__
        raise
    except SystemExit as e:
        script_exitcode = e.code
        outcome = 'system_exit'
        exception_type = type(e).__name__
        raise
    except Exception as e:
        outcome = 'error'
        exception_type = type(e).__name__
        raise
    else:
        exported = newvars.get('__export__')        
        if exported:
            ## __export__ = '*' will export all
            if '*' == exported:
                _vars.update(newvars)
                export_count = len(newvars)
            else:
                for key in exported:
                    _vars[key] = newvars[key]
                export_count = len(exported)
            logger.debug(
                'Exported script variables (path=%s, count=%d)',
                absfile,
                export_count,
            )
        _vars['_sshscriptstacks_'] = newvars['_sshscriptstacks_']
        outcome = 'completed'
        script_exitcode = 0
    finally:
        ## restore sys.path
        if scriptFolderInsertedToSysPath:
            sys.path.remove(scriptFolder)
        the_session.close()
        del the_session
        logger.debug(
            'Script file finished '
            '(path=%s, outcome=%s, exit_code=%s, exception_type=%s, duration_ms=%d)',
            absfile,
            outcome,
            script_exitcode,
            exception_type,
            int((time.monotonic() - started_at) * 1000),
        )

    return exitcode


def run_script(script,varGlobals=None,showScript=False):
    the_session = Session()
    started_at = time.monotonic()
    outcome = 'failed'
    exception_type = None
    logger.debug('Starting in-memory script')
    try:
        ## this is a blocking call
        result = the_session.run(script,vars=varGlobals,showScript=showScript)
        outcome = 'completed'
        return result
    except BaseException as exc:
        exception_type = type(exc).__name__
        raise
    finally:
        the_session.close()
        logger.debug(
            'In-memory script finished '
            '(outcome=%s, exception_type=%s, duration_ms=%d)',
            outcome,
            exception_type,
            int((time.monotonic() - started_at) * 1000),
        )

def main():
    ## v2.0.3, only one .spy file is allowed, this makes no sense
    ## --run-order, 
    #parser.add_argument('--run-order', dest='showRunOrder', action='store_true',
    #                    default=False,
    #                    help='show the files to run in order, no execution.')

    ## Console logging is a CLI concern; importing sshscript remains silent.
    set_logger()

    import argparse

    ## REF: https://stackoverflow.com/questions/15753701/how-can-i-pass-a-list-as-a-command-line-argument-with-argparse
    parser = argparse.ArgumentParser(description='SSHScript: automation tools for Subprocess and SSH')


    parser.add_argument('--script','-s', dest='showScript', action='store_true',
                        default=False,
                        help='show the converted python script only, no execution.')
    
    parser.add_argument('--verbose','-v', dest='verbose', action='store_true',
                        default=False,
                        help='dump stdout,stderr to console.')   

    parser.add_argument('--stderr', dest='verbose_stderr', action='store_true',
                        default=False,
                        help='dump stderr only to console.')   


    parser.add_argument('--debug','-d', dest='debug', nargs='*',
                        help='enable debug logging (level 10 by default)')


    parser.add_argument('path', action='store', nargs='?', default='_',
                        help='path of .spy files or folders')


    ## new on v1.1.17
    parser.add_argument('--version', dest='version', action='store_true',default=False,
                        help='dump the version number')

    ## new on v2.0.2
    parser.add_argument('--check', dest='checkversion', action='store_true',default=False,
                        help='check the last version of SSHScript (need internet)')

    ## new on v3.1.0
    parser.add_argument(
        '--traceback',
        dest='show_traceback',
        action='store_true',
        default=False,
        help=(
            'show the full exception traceback; '
            'it may expose script source, commands, or secrets'
        ),
    )
    args, unknown = parser.parse_known_args()
   
    ## add unknown arguments to sys.argv
    del sys.argv[1:] 
    sys.argv.extend(unknown)

    def get_current_version():
        return __version__

    ## handle the contradiction between args.debug and args.paths
    if args.path == '_':
        if args.debug and len(args.debug) == 1:
            ## sshscript.py  --debug unittest-v2.0.3/A01onedollar.spy 
            args.path = args.debug[0]
            args.debug = 10
        elif args.debug and len(args.debug) > 1:
            ## sshscript.py  --debug 10  unittest-v2.0.3/A01onedollar.spy
            args.path = args.debug[1]
            args.debug = int(args.debug[0])
        else:
            args.path = None
    elif args.debug is not None:
        if len(args.debug) == 0:
            ## sshscript.py unittest-v2.0.3/A01onedollar.spy --debug
            args.debug = 10
        elif len(args.debug) > 0:
            ## sshscript.py unittest-v2.0.3/A01onedollar.spy --debug 10
            args.debug = int(args.debug[0])
    ## handling starts
    if (args.version):
        print(get_current_version())
    elif (args.checkversion):
        current_version = get_current_version()
        import urllib.request
        import json
        info = json.loads(urllib.request.urlopen("https://iapyeh.github.io/sshscript/info.json",timeout=3).read())
        mime = [x for x in current_version.split('.')]
        current = [x for x in info['version'].split('.')]
        print(f'The latest release of SSHScript is {info["version"]}, you have version {current_version} installed.')
        if not current_version == info['version']:
            canupgrade = True
            for i in range(3):
                if mime[i] > current[i]:
                    canupgrade = False
                    break
            if canupgrade:
                print(f"Installed SSHScript Version is \"{current_version}\", SSHScript has new version \"{info['version']}\".")
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
            run_file(args.path,
                showScript=args.showScript
                )
        except SSHScriptExit as e:
            sys.exit(e.errno)
        except SSHScriptException as e:
            if args.show_traceback:
                logger.exception(
                    'SSHScript failed (exception_type=%s, exit_code=%s)',
                    type(e).__name__,
                    e.errno,
                )
            else:
                logger.error(
                    'SSHScript failed (exception_type=%s, exit_code=%s); '
                    'rerun with --traceback for details',
                    type(e).__name__,
                    e.errno,
                )
            sys.exit(e.errno)
        except SyntaxError as exc:
            if args.show_traceback:
                logger.exception(
                    'SSHScript CLI failed (exception_type=%s)',
                    type(exc).__name__,
                )
            else:
                # Syntax diagnostics are useful without an internal stack.
                # Python renders the mapped filename, line, source and caret.
                sys.stderr.writelines(
                    traceback.format_exception_only(
                        type(exc),
                        exc,
                    )
                )
            sys.exit(1)
        except Exception as exc:
            # Exception messages and source lines can contain command arguments,
            # passwords, or tokens. Keep the default CLI record diagnostic but
            # payload-free; the process still exits with a failure status below.
            if args.show_traceback:
                logger.exception(
                    'SSHScript CLI failed (exception_type=%s)',
                    type(exc).__name__,
                )
            else:
                logger.error(
                    'SSHScript CLI failed (exception_type=%s); '
                    'rerun with --traceback for details',
                    type(exc).__name__,
                )
            sys.exit(1)
        else:
            sys.exit(0)
    elif sys.stdout.isatty():
        # check new version, new from 1.1.13
        current_version = get_current_version()
        if current_version: print(f'Version:{current_version}')
        
        parser.print_help()
    
if __name__ == '__main__':
    main()
