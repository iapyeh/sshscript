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
import __main__
import logging
import os
import re
import shlex
import sys
import threading


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


def command_requires_shell(command:str):
    """Return whether *command* needs POSIX shell interpretation and why.

    Detection is quote-aware: shell operators are ignored inside single and
    double quotes, while parameter and command expansion remain active inside
    double quotes.  The returned reasons are intended for diagnostics and
    tests; callers should normally only use the boolean value.
    """
    if not isinstance(command, str):
        raise TypeError(f'command must be str, not {type(command).__name__}')

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


_SENSITIVE_KEY_PATTERN = (
    r'password|passwd|pwd|passphrase|token|access[_-]?token|api[_-]?key|'
    r'secret|client[_-]?secret|private[_-]?key'
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r'-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?'
    r'-----END [^-\r\n]*PRIVATE KEY-----',
    re.IGNORECASE | re.DOTALL,
)
_URL_CREDENTIAL_RE = re.compile(
    r'(?P<prefix>[a-z][a-z0-9+.-]*://[^\s/@:]+:)'
    r'(?P<secret>[^\s/@]+)(?P<suffix>@)',
    re.IGNORECASE,
)
_AUTHORIZATION_RE = re.compile(
    r'(?P<prefix>\bauthorization\s*[:=]\s*(?:bearer|basic)?\s*)'
    r'(?P<secret>"[^"]*"|\'[^\']*\'|[^\s,;]+)',
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    rf'(?P<prefix>\b(?:{_SENSITIVE_KEY_PATTERN})\b\s*[:=]\s*)'
    r'(?P<secret>"[^"]*"|\'[^\']*\'|[^\s,;]+)',
    re.IGNORECASE,
)
_SENSITIVE_OPTION_RE = re.compile(
    rf'(?P<prefix>--?(?:{_SENSITIVE_KEY_PATTERN})(?:\s+|=))'
    r'(?P<secret>"[^"]*"|\'[^\']*\'|[^\s,;]+)',
    re.IGNORECASE,
)


def redact_sensitive(value):
    """Return *value* with common credentials replaced by ``<redacted>``.

    The helper is intentionally conservative and is a final safety net rather
    than permission to log arbitrary commands or input. Password input and
    complete command text should still be omitted whenever possible.
    """
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = _PRIVATE_KEY_BLOCK_RE.sub('<redacted-private-key>', text)
    text = _URL_CREDENTIAL_RE.sub(
        lambda match: (
            f'{match.group("prefix")}<redacted>{match.group("suffix")}'
        ),
        text,
    )
    text = _AUTHORIZATION_RE.sub(
        lambda match: f'{match.group("prefix")}<redacted>',
        text,
    )
    text = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f'{match.group("prefix")}<redacted>',
        text,
    )
    return _SENSITIVE_OPTION_RE.sub(
        lambda match: f'{match.group("prefix")}<redacted>',
        text,
    )


def command_summary(command):
    """Return safe metadata about a command without returning its arguments."""
    command_type = type(command).__name__
    if isinstance(command, str):
        char_count = len(command)
        try:
            argv = shlex.split(command, posix=True)
        except ValueError:
            argv = ()
            arg_count = None
        else:
            arg_count = len(argv)
    elif isinstance(command, (list, tuple)):
        char_count = None
        argv = command
        arg_count = len(argv)
    else:
        return {
            'type': command_type,
            'executable': None,
            'char_count': None,
            'arg_count': None,
        }

    executable = None
    if argv:
        first = argv[0]
        if isinstance(first, str):
            safe_first = redact_sensitive(first)
            executable = safe_first.rsplit('/', 1)[-1]
            executable = re.sub(r'[\x00-\x1f\x7f]', '?', executable)[:128]

    return {
        'type': command_type,
        'executable': executable,
        'char_count': char_count,
        'arg_count': arg_count,
    }


## default logger


## ensure this logger is singleton
global logger
logger = None
try:
    ## this module has been imported somewhere
    logger = __main__._sshscript_logger
except AttributeError:
    pass


class WrappedLogger:
    """Proxy a logger while keeping SSHScript's configuration API compatible."""

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s '
        '%(message)s',
        '%Y-%m-%d %H:%M:%S',
    )

    def __init__(self, _logger):
        global logger
        if logger is not None:
            raise RuntimeError(
                'logger is a singleton; use errorutils.get_logger() instead'
            )
        self._logger = _logger
        self.tty_handler = None
        self._propagate_before_tty = None
        self._configure_library_logger()
        self.reset_debug()
        ## make this instance be singleton when imported by another module name
        __main__._sshscript_logger = self

    def __getattr__(self, name):
        return getattr(self._logger, name)

    def _configure_library_logger(self):
        """Keep library imports silent without blocking application handlers."""
        if not self._logger.handlers:
            self._logger.addHandler(logging.NullHandler())

    def reset_debug(self, level=logging.INFO):
        debug_level = os.environ.get('DEBUG')
        if debug_level:
            try:
                level = int(debug_level)
            except ValueError:
                level = logging.DEBUG
        if isinstance(level, int) and 0 < level < logging.DEBUG:
            level = logging.DEBUG
        self._logger.setLevel(level)

    def add_console_handler(self, stream=None):
        """Explicitly add one formatted console handler."""
        if stream is None:
            stream = sys.stderr
        for handler in self._logger.handlers:
            if (
                isinstance(handler, logging.StreamHandler)
                and getattr(handler, 'stream', None) is stream
            ):
                if getattr(handler, '_sshscript_console_handler', False):
                    self.tty_handler = handler
                    if self._propagate_before_tty is None:
                        self._propagate_before_tty = self._logger.propagate
                    self._logger.propagate = False
                return handler

        handler = logging.StreamHandler(stream)
        handler._sshscript_console_handler = True
        # Retain the old private marker for callers that inspect configured
        # handlers, even when the explicit CLI stream is not a TTY.
        handler._sshscript_tty_handler = True
        self.add_handler(handler)
        self.tty_handler = handler
        if self._propagate_before_tty is None:
            self._propagate_before_tty = self._logger.propagate
        self._logger.propagate = False
        return handler

    def dump_to_tty(self, stream=None):
        """Add one console handler only when the selected stream is a TTY."""
        if stream is None:
            stream = sys.stdout
        if not getattr(stream, 'isatty', lambda: False)():
            return None
        return self.add_console_handler(stream)

    def mute_tty(self):
        """Remove SSHScript's console handler; safe to call repeatedly."""
        handler = self.tty_handler
        if handler is None:
            return
        if handler in self._logger.handlers:
            self._logger.removeHandler(handler)
        handler.close()
        self.tty_handler = None
        if self._propagate_before_tty is not None:
            self._logger.propagate = self._propagate_before_tty
            self._propagate_before_tty = None

    def set_logger(self, logger, keep_level=True):
        current_logger = self._logger
        current_level = current_logger.getEffectiveLevel()
        self.mute_tty()
        self._logger = logger
        self._propagate_before_tty = None
        if keep_level:
            self._logger.setLevel(current_level)

    def reset_formatter(self, formatter):
        if not isinstance(formatter, logging.Formatter):
            raise TypeError('formatter must be an instance of logging.Formatter')
        WrappedLogger.formatter = formatter
        for handler in self._logger.handlers:
            handler.setFormatter(formatter)

    def add_handler(self, handler):
        if not isinstance(handler, logging.Handler):
            raise TypeError('handler must be an instance of logging.Handler')
        if handler.formatter is None:
            handler.setFormatter(WrappedLogger.formatter)
        if handler not in self._logger.handlers:
            self._logger.addHandler(handler)
        return handler


def log_debug(message, *args, **kwargs):
    """Compatibility wrapper for lazy ``logger.debug`` calls."""
    get_logger().debug(message, *args, **kwargs)


def thread_id_filter(record):
    """Add thread ID to log records.
    
    Args:
        record: The log record to modify
        
    Returns:
        bool: True so logging continues processing the record.
    """
    record.thread_id = threading.get_native_id()
    return True


def set_logger(userlogger=None,logname=None):
    """Configure the global logger with appropriate handlers and level.
    
    Args:
        userlogger (logging.Logger, optional): Logger to use instead of
            creating a new one. Defaults to None.
        logname (str, optional): Name for a newly created default logger.
        
    Returns:
        logging.Logger: The configured logger instance
    """
    if isinstance(userlogger,str):
        logname = userlogger
        userlogger = None

    global logger
    if logger is None:
        logger = WrappedLogger(logging.getLogger(logname or 'sshscript'))
    
    if userlogger is not None:
        logger.set_logger(userlogger,keep_level=False) ## use userlogger's level
    else:
        ## set_logger() is the explicit CLI/application console configuration
        ## path. Merely importing SSHScript or calling get_logger() stays silent.
        logger.add_console_handler()

    if os.environ.get('DEBUG'): logger.reset_debug()

    return userlogger if userlogger is not None else logger

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
