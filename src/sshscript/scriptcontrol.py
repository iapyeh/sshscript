"""Script completion and interactive-scope control, separate from execution errors."""
from contextvars import ContextVar
from typing import Any


class ScriptResult(dict[str, Any]):
    """Executed namespace plus completion status; also returned after stop()."""
    def __init__(self, namespace: dict[str, Any], *, exitcode: int = 0,
                 stopped: bool = False, message: str = "") -> None:
        super().__init__(namespace)
        self.exitcode = exitcode
        self.stopped = stopped
        self.message = message


class ScriptStopped(BaseException):
    """Internal normal-completion signal, caught by the nearest script runner."""
    def __init__(self, code: int = 0, message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


script_active: ContextVar[bool] = ContextVar("sshscript_script_active", default=False)


def stop_script(code: int = 0, message: str = "") -> None:
    if not script_active.get():
        raise RuntimeError("stop() requires a running script; use exit() to leave a console layer")
    if isinstance(code, bool) or not isinstance(code, int):
        raise TypeError("stop code must be an integer")
    if not isinstance(message, str):
        raise TypeError("stop message must be a string")
    raise ScriptStopped(code, message)
