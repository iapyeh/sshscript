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

class SSHScriptError(Exception):
    def __init__(self, message,code=1):
        super().__init__(message)
        self.message = message
        self.code = code
    def __str__(self):
        return f'<{self.__class__.__name__}({self.code}){self.message}>'
class SSHScriptBreak(SSHScriptError):
    pass
class SSHScriptExit(SSHScriptError):
    pass
class SSHScriptCareful(SSHScriptError):
    pass

import paramiko
import logging
import os, sys
from paramiko.common import (
    DEBUG,
)

global logger
# default logger
logger = paramiko.util.get_logger('sshscript')
def getLogger():
    global logger
    return logger

def setLogger(_logger):
    global logger
    logger = _logger

def setupLogger(_logger=None):
    global logger
    if _logger is None:
        logger = getLogger()
        # default is WARNING
        if os.environ.get('DEBUG'): logger.setLevel(DEBUG)         

        if sys.stdout.isatty():
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter('%(asctime)s:%(message)s',"%Y-%m-%d %H:%M:%S")) 
            logger.addHandler(handler)
            logger.log(DEBUG,'sys.stdout added to logger')
    else:
        setLogger(_logger)
    return logger