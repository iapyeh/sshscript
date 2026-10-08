"""Reject unsupported interpreters before importing SSHScript features."""
import sys


def require_python(cli=False):
    if sys.version_info < (3, 11):
        message = (
            "SSHScript requires Python 3.11 or newer.\n"
            "Detected Python %s at %s."
            % ('.'.join(map(str, sys.version_info[:3])), sys.executable)
        )
        if cli:
            raise SystemExit(message)
        raise ImportError(message)
