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
import re
import shlex
class SSHScriptException(Exception):
    """Base exception class for SSHScript errors.
    
    Attributes:
        message (str): Error message describing what went wrong
        code (int): Error code associated with the error (default: 1)
    """
    def __init__(self, message,errno=1):
        super().__init__(message)
        self.message = message
        self.errno = errno
    def __str__(self):
        return f'{self.message}(#{self.errno})'

class SSHScriptBreak(SSHScriptException):
    """Exception raised when a break statement is encountered in SSHScript."""
    pass

class SSHScriptExit(SSHScriptException):
    """Exception raised when an exit statement is encountered in SSHScript."""
    pass

def dumpScript(source,tb_lineno=None,linerange=10):
    """Print a script with line numbers and error highlighting.
    
    Args:
        source (str): The source code to display
        tb_lineno (int, optional): Line number where the error occurred. Defaults to None.
        linerange (int, optional): Number of lines to show before and after the error line. Defaults to 10.
    """
    lines = source.splitlines()
    for i,line in enumerate(lines):
        lineno = i + 1
        if (tb_lineno is None) or (abs(lineno - tb_lineno) <= linerange):
            print(f'{lineno:3d}: {line}')
        if lineno == tb_lineno:
            print('     '+'^' * len(line))

def command_is_shell(command)->bool:
    """Check if a command is a shell command or 'script', which invoking an interactive process.
    Args:
        command (str): The command to check
        
    Returns:
        bool: True if the command is a shell command (sh, bash, ash, csh, tcsh, fish, ksh, zsh)
    """
    args = shlex.split(command)
    ## Note: only sh, bash, zsh were tested by the author
    shellnames = ('sh','bash','ash','csh','tcsh','fish','ksh','zsh','script')
    isShell = False
    for arg in args[:2]:
        paths = arg.split('/')
        if paths[-1] in shellnames:
            isShell = True
            break
    return isShell


_SHELL_BUILTINS_AND_RESERVED_WORDS = {
    '.', 'alias', 'bg', 'break', 'case', 'cd', 'command', 'continue', 'do',
    'done', 'elif', 'else', 'esac', 'eval', 'exec', 'exit', 'export', 'false',
    'fc', 'fg', 'fi', 'for', 'getopts', 'hash', 'if', 'jobs', 'kill', 'local',
    'pwd', 'read', 'readonly', 'return', 'set', 'shift', 'source', 'test',
    'then', 'time', 'times', 'trap', 'true', 'type', 'typeset', 'ulimit',
    'umask', 'unalias', 'unset', 'until', 'wait', 'while', '{', '}', '!',
}
_SHELL_ASSIGNMENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
_PARAMETER_START = set('_0123456789?*#$!@-({')


def command_requires_shell(command):
    """Return whether *command* needs POSIX shell interpretation and why.

    Detection is quote-aware: shell operators are ignored inside single and
    double quotes, while parameter and command expansion remain active inside
    double quotes.  The returned reasons are intended for diagnostics and
    tests; callers should normally only use the boolean value.

    A list/tuple command is already structured argv and therefore never uses a
    shell automatically.
    """
    if isinstance(command, (list, tuple)):
        return False, []
    if not isinstance(command, str):
        raise TypeError(f'command must be str, list, or tuple, not {type(command).__name__}')

    reasons = []

    def add(reason):
        if reason not in reasons:
            reasons.append(reason)

    state = 'unquoted'
    escaped = False
    word_start = True
    i = 0
    length = len(command)

    while i < length:
        char = command[i]
        next_char = command[i + 1] if i + 1 < length else ''

        if escaped:
            escaped = False
            word_start = False
            i += 1
            continue

        if state == 'single':
            if char == "'":
                state = 'unquoted'
            i += 1
            continue

        if state == 'double':
            if char == '"':
                state = 'unquoted'
            elif char == '\\' and next_char in '$`"\\\n':
                escaped = True
            elif char == '$' and next_char and (
                next_char.isalnum() or next_char in _PARAMETER_START
            ):
                add('parameter-expansion' if next_char != '(' else 'command-substitution')
            elif char == '`':
                add('command-substitution')
            i += 1
            continue

        if char == '\\':
            escaped = True
        elif char == "'":
            state = 'single'
            word_start = False
        elif char == '"':
            state = 'double'
            word_start = False
        elif char in '\r\n':
            add('newline')
            word_start = True
        elif char.isspace():
            word_start = True
        elif char == '$' and next_char and (
            next_char.isalnum() or next_char in _PARAMETER_START
        ):
            add('parameter-expansion' if next_char != '(' else 'command-substitution')
            word_start = False
        elif char == '`':
            add('command-substitution')
            word_start = False
        elif char == '|':
            add('pipeline' if next_char != '|' else 'logical-operator')
            word_start = True
        elif char == '&':
            add('logical-operator' if next_char == '&' else 'background')
            word_start = True
        elif char == ';':
            add('command-separator')
            word_start = True
        elif char in '<>':
            add('redirection')
            word_start = True
        elif char in '*?[':
            add('glob')
            word_start = False
        elif char == '~' and word_start:
            add('tilde-expansion')
            word_start = False
        elif char == '#' and word_start:
            add('comment')
            word_start = False
        elif char in '()':
            add('subshell')
            word_start = char == ')'
        else:
            word_start = False
        i += 1

    if escaped or state != 'unquoted':
        add('incomplete-quoting')

    try:
        argv = shlex.split(command, posix=True)
    except ValueError:
        argv = []
    if argv:
        if _SHELL_ASSIGNMENT.match(argv[0]):
            add('assignment')
        elif argv[0] in _SHELL_BUILTINS_AND_RESERVED_WORDS:
            add('shell-builtin')

    return bool(reasons), reasons


def command_is_sudo(command)->bool:
    """Check if a command uses sudo or su.
    
    Args:
        command (str): The command to check
        
    Returns:
        bool: True if the command uses sudo or su
    """
    args = shlex.split(command)
    ## Note: only sh, bash, zsh were tested by the author
    names = ('su','sudo')
    name = False
    for arg in args:
        paths = arg.split('/')
        if paths[-1] in names:
            name = paths[-1]
            break
    return name


import logging, threading
import os, sys,__main__
from logging import DEBUG
assert DEBUG == 10
DEBUG8 = 8
## default logger


## ensure this logger is singleton
global logger
logger = None
try:
    ## this moudle has been imported somewhere
    logger = __main__._sshscript_logger
except AttributeError:
    pass
class WrappedLogger:
    #handler.addFilter(thread_id_filter)
    #handler.setFormatter(logging.Formatter('%(thread_id)d:%(asctime)s:%(message)s',"%Y-%m-%d %H:%M:%S")) 
    formatter = logging.Formatter('%(asctime)s:%(message)s',"%Y-%m-%d %H:%M:%S")
    private_attrs = ('_logger','reset_debug','add_handler','tty_handler','dump_to_tty','mute_tty','set_logger','reset_formatter')
    def __init__(self, _logger):
        global logger
        if logger is not None:
            raise RuntimeError('logger is a singleton, use errutils.get_logger() instead')
        self._logger = _logger
        self.reset_debug()
        self.dump_to_tty()
        ## make this instance be singleton when "import "
        __main__._sshscript_logger = self

    def __getattribute__(self, name):
        # Allow access to private attributes directly
        if name in WrappedLogger.private_attrs:
            return object.__getattribute__(self, name)
        else:
            return object.__getattribute__(self._logger, name)
        
    def reset_debug(self,level=logging.INFO):
        if os.environ.get('DEBUG'):
            try:
                level = int(os.environ['DEBUG'])
            except ValueError:
                level = DEBUG ## default is 10 (logging.DEBUG)
            self._logger.setLevel(level)
        else:
            self._logger.setLevel(level)

    def dump_to_tty(self):
        if sys.stdout.isatty():
            self.tty_handler = logging.StreamHandler(sys.stdout)
            self.add_handler(self.tty_handler)

    def mute_tty(self):
        self._logger.removeHandler(self.tty_handler)

    def set_logger(self,logger,keep_level=True):
        current_logger = self._logger
        self._logger = logger
        if keep_level:
            ## copy level
            self._logger.setLevel(current_logger.getEffectiveLevel())

    def reset_formatter(self,formatter):
        WrappedLogger.formatter = formatter
        for h in self._logger.handlers:
            h.formatter = formatter

    def add_handler(self,handler):
        if handler.formatter is None: handler.formatter = WrappedLogger.formatter
        self._logger.addHandler(handler)

def log_debug(mesg,*args):
    """Log a debug message at DEBUG level.
    
    Args:
        mesg (str): The message to log
        *args: Additional arguments to format the message
    """
    logger.log(DEBUG,mesg, *args)

def log_debug_8(mesg,*args):
    """Log a debug message at DEBUG8 level (level 8).
    
    Args:
        mesg (str): The message to log
        *args: Additional arguments to format the message
    """
    logger.log(DEBUG8, mesg,*args)

def thread_id_filter(record):
    """Add thread ID to log records.
    
    Args:
        record: The log record to modify
        
    Returns:
        The modified log record with thread_id added
    """
    record.thread_id = threading.get_native_id()
    return record

def set_logger(userlogger=None,logname=None):
    """Configure the global logger with appropriate handlers and level.
    
    Args:
        _logger (logging.Logger, optional): Logger to use instead of creating a new one. Defaults to None.
        
    Returns:
        logging.Logger: The configured logger instance
    """
    if isinstance(userlogger,str):
        logname = userlogger
        userlogger = None

    global logger
    if logger is None:
        logger = WrappedLogger(logging.getLogger(logname or 'sshscript'))
    
    if userlogger:
        logger.set_logger(userlogger,keep_level=False) ## use userlogger's level

    if os.environ.get('DEBUG'): logger.reset_debug()

    return userlogger if userlogger else logger

def get_logger():
    """Get the global logger instance.
    
    Returns:
        logging.Logger: The global logger instance
    """
    global logger
    if logger is None:
        logger = WrappedLogger(logging.getLogger('sshscript'))
    return logger

## v2.0.3 added (by https://stackoverflow.com/questions/9836425/equivelant-to-rindex-for-lists-in-python)
def listRightIndex(alist, value):
    """Find the rightmost index of a value in a list.
    
    Args:
        alist (list): The list to search in
        value: The value to find
        
    Returns:
        int: The rightmost index of the value in the list, or -1 if not found
    """
    return len(alist) - alist[-1::-1].index(value) -1

## constants. for detecting if "exitcode" has been retrieved
EXITCODE_DEFAULT = 255
