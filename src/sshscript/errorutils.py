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
        return f'[Errno {self.errno}] {self.message}'

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
import os, sys
from logging import DEBUG
assert DEBUG == 10
DEBUG8 = 8
global logger
## default logger
logger = logging.getLogger('sshscript')

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

def set_logger(_logger=None):
    """Configure the global logger with appropriate handlers and level.
    
    Args:
        _logger (logging.Logger, optional): Logger to use instead of creating a new one. Defaults to None.
        
    Returns:
        logging.Logger: The configured logger instance
    """
    global logger
    if _logger is None:
        logger = get_logger()
        if os.environ.get('DEBUG'):
            try:
                level = int(os.environ['DEBUG'])
            except ValueError:
                level = DEBUG ## default is 10 (logging.DEBUG)
            logger.setLevel(level)

        if sys.stdout.isatty():
            handler = logging.StreamHandler(sys.stdout)
            #handler.addFilter(thread_id_filter)
            #handler.setFormatter(logging.Formatter('%(thread_id)d:%(asctime)s:%(message)s',"%Y-%m-%d %H:%M:%S")) 
            handler.setFormatter(logging.Formatter('%(asctime)s:%(message)s',"%Y-%m-%d %H:%M:%S")) 
            logger.addHandler(handler)
            logger.log(DEBUG,'sys.stdout added to logger')
    else:
        logger = _logger
    return logger

def get_logger():
    """Get the global logger instance.
    
    Returns:
        logging.Logger: The global logger instance
    """
    global logger
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