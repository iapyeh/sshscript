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

import ast
import traceback

try:
    ast.unparse
except AttributeError:
    try:
        import astunparse
    except ImportError:
        traceback.print_exc()
        print('Python version less than 3.9 require "astunparse" to be installed. Please install it by "pip install astunparse"')
        raise
    else:
        setattr(ast,'unparse', astunparse.unparse)

if __package__:
    from . import sshscript
    from . import session
    from . import errorutils
else:
    import sshscript
    import session
    import errorutils

__version__ = sshscript.__version__
run_file = sshscript.run_file
run_script = sshscript.run_script
Session = session.Session

set_logger = errorutils.set_logger
get_logger = errorutils.get_logger
SSHScriptException = errorutils.SSHScriptException

## sshscript v3.0 no more support mutltiple *.spy executions.
## so, "____sshscript____" has removed.
## then, this "run" is no more necesary
#def run(script,_global=None,_local=None,showScript=False):
#    if _global is None:
#        _global ={'____sshscript____':[]}
#    else:
#        _global['____sshscript____']=[]
#    script = script + '\n\n____sshscript____.append(($.stdout,$.stderr))'
#    run_script(script,_global,_local,showScript)
#    if showScript:
#        return None,None
#    else:
#        return _global['____sshscript____'][0]

__all__ = ['run_file', 'run_script', 'Session','get_logger','set_logger','SSHScriptException']
