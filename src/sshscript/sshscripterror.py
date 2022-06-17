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

class SSHScriptError(Exception):
      def __init__(self, message,code=1):
          super().__init__(message)
          self.code = code
class SSHScriptExit(Exception):
      def __init__(self,code=0):
          super().__init__('exit')
          self.code = code