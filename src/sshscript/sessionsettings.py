"""Validated Session settings and context-local defaults."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import os
from paramiko import MissingHostKeyPolicy
from types import MappingProxyType

DEFAULTS = MappingProxyType(dict(check=False, verbose=False, verbose_stderr=False,
                                log_level=logging.INFO, policy=None,
                                known_hosts='parent', known_hosts_path=None))
UNSET = object()
_defaults = ContextVar('sshscript_execution_defaults', default={})


def validate(values):
    result = dict(values)
    for key, value in result.items():
        if key not in DEFAULTS:
            raise ValueError(f'unknown Session setting: {key}')
        if key == 'policy':
            if value is not None and not (
                isinstance(value, MissingHostKeyPolicy) or
                (isinstance(value, type) and issubclass(value, MissingHostKeyPolicy))
            ):
                raise TypeError('policy must be a MissingHostKeyPolicy instance, subclass, or None')
        elif key == 'known_hosts':
            if not isinstance(value, str):
                raise TypeError('known_hosts must be local, parent, or chain')
            if value not in ('local', 'parent', 'chain'):
                raise ValueError('known_hosts must be local, parent, or chain')
        elif key == 'known_hosts_path':
            if value is not None:
                if not isinstance(value, (str, os.PathLike)):
                    raise TypeError('known_hosts_path must be a text path or None')
                value = os.fspath(value)
                if not isinstance(value, str):
                    raise TypeError('known_hosts_path must be a text path or None')
                if not value or '\x00' in value:
                    raise ValueError('known_hosts_path must be nonempty and contain no NUL')
                result[key] = value
        elif key == 'log_level':
            if isinstance(value, str):
                value = logging.getLevelName(value.upper())
                if not isinstance(value, int):
                    raise ValueError("unknown log_level name")
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError('log_level must be a logging level number or name')
            if value < 0:
                raise ValueError('log_level must be nonnegative')
            result[key] = value
        elif not isinstance(value, bool):
            raise TypeError(f'{key} must be bool')
    return result


def root_defaults():
    # Preserve explicit application logging and legacy environment configuration.
    if __package__:
        from .errorutils import get_logger
    else:
        from errorutils import get_logger
    values = dict(DEFAULTS, log_level=get_logger().getEffectiveLevel(),
                  verbose=bool(os.environ.get('VERBOSE')),
                  verbose_stderr=bool(os.environ.get('VERBOSE_STDERR')))
    values.update(_defaults.get())
    return values


@contextmanager
def execution_defaults(**values):
    token = _defaults.set(dict(_defaults.get(), **validate(values)))
    try:
        yield
    finally:
        _defaults.reset(token)


class SessionLogger:
    """Filter by session policy without changing a shared logger's level.

    Application handler levels, logger filters, and logging.disable still apply.
    """
    def __init__(self, settings):
        self.settings = settings

    def log(self, level, message, *args, **kwargs):
        if level < self.settings['log_level']:
            return
        if __package__:
            from .errorutils import get_logger
        else:
            from errorutils import get_logger
        target = get_logger()._logger
        if target.disabled or level <= logging.root.manager.disable:
            return
        # _log creates and handles a record without the shared isEnabledFor gate.
        target._log(level, message, args, **kwargs)

    def debug(self, msg, *args, **kw): self.log(logging.DEBUG, msg, *args, **kw)
    def info(self, msg, *args, **kw): self.log(logging.INFO, msg, *args, **kw)
    def warning(self, msg, *args, **kw): self.log(logging.WARNING, msg, *args, **kw)
    def error(self, msg, *args, **kw): self.log(logging.ERROR, msg, *args, **kw)
    def critical(self, msg, *args, **kw): self.log(logging.CRITICAL, msg, *args, **kw)
    def exception(self, msg, *args, **kw):
        kw.setdefault('exc_info', True)
        self.error(msg, *args, **kw)
    def isEnabledFor(self, level):
        return level >= self.settings['log_level']
