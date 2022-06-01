class SSHScriptError(Exception):
      def __init__(self, message,code=1):
          super().__init__(message)
          self.code = code
class SSHScriptExit(Exception):
      def __init__(self,code=0):
          super().__init__('exit')
          self.code = code