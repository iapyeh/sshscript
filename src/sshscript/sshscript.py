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
import time
import traceback
## starts from 3.1, asyncio is introduced.
__version__ = "3.1.0"

# set here used in sshscriptdollar
import warnings
def warning_on_one_line(message, category, filename, lineno, file=None, line=None):
    return '%s:%s: %s: %s\n' % (filename, lineno, category.__name__, message)
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
spy_imports = spyimporter.spy_imports

def run_file(
    script_path,
    vars=None,
    showScript=False,
) -> int:
    """Execute one Python or ``.spy`` script file in a new local session.

    ``script_path`` must identify one existing regular file; directories,
    globs, and iterables of paths are not accepted.  Scripts that need code
    from other files should use SSHScript include syntax or Python imports.

    Args:
        script_path: A string or ``os.PathLike`` path to one script file.
        vars: Optional initial names exposed to the script.
        showScript: Convert and display the script without executing it.

    Returns:
        ``0`` after normal completion, or the status supplied to
        ``$.break(status)``.

    Raises:
        TypeError: If ``script_path`` is not a string or path-like object.
        RuntimeError: If the path is missing or is not a regular file.
        SSHScriptExit: If the script calls ``$.exit(status)``.
    """
    if not isinstance(script_path, (str, os.PathLike)):
        raise TypeError('script_path must be str or os.PathLike')
    absfile = os.path.abspath(os.fspath(script_path))
    if not os.path.exists(absfile):
        raise RuntimeError(f'{absfile} not found')
    if not os.path.isfile(absfile):
        raise RuntimeError(f'{absfile} is not a file')

    script_vars = dict(vars or {})
    script_vars['sshscript'] = sshscript_module
    session = Session()
    exitcode = 0
    started_at = time.monotonic()
    outcome = 'failed'
    script_exitcode = None
    exception_type = None
    script_folder = os.path.dirname(absfile)
    inserted_path = False
    logger.debug('Starting script file (path=%s)', absfile)

    try:
        with open(absfile, 'rb') as fd:
            script = fd.read().decode('utf-8', 'replace')

        if script_folder not in sys.path:
            inserted_path = True
            sys.path.insert(0, script_folder)

        script_vars['__name__'] = '__main__'
        script_vars['__file__'] = absfile
        with spyimporter.spy_imports():
            session.run(
                script,
                script_vars,
                showScript=showScript,
            )
    except SSHScriptBreak as exc:
        exitcode = exc.errno
        script_exitcode = exc.errno
        outcome = 'break'
    except SSHScriptExit as exc:
        script_exitcode = exc.errno
        outcome = 'exit'
        raise
    except SSHScriptException as exc:
        script_exitcode = exc.errno
        outcome = 'sshscript_error'
        exception_type = type(exc).__name__
        raise
    except BaseException as exc:
        outcome = 'error'
        exception_type = type(exc).__name__
        raise
    else:
        outcome = 'completed'
        script_exitcode = 0
    finally:
        if inserted_path:
            sys.path.remove(script_folder)
        session.close()
        logger.debug(
            'Script file finished '
            '(path=%s, outcome=%s, exit_code=%s, '
            'exception_type=%s, duration_ms=%d)',
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
    ## Console logging is a CLI concern; importing sshscript remains silent.
    set_logger()
    warnings.formatwarning = warning_on_one_line

    import argparse

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
                        help='path of one Python or .spy script file')


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

    ## handle the contradiction between args.debug and args.path
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

        try:
            exitcode = run_file(
                args.path,
                showScript=args.showScript,
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
            sys.exit(exitcode)
    elif sys.stdout.isatty():
        # check new version, new from 1.1.13
        current_version = get_current_version()
        if current_version: print(f'Version:{current_version}')
        
        parser.print_help()
    
if __name__ == '__main__':
    main()
