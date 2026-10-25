"""Resolve a documented subset of OpenSSH config without opening connections.

Match/Include/canonicalization are rejected, rather than partially interpreted.
Proxy commands are only started by Session.connect(), never by this resolver.
"""
import getpass
import os
import re
import shlex
from urllib.parse import urlsplit
import warnings
import difflib
import inspect

import paramiko

if __package__:
    from .sessionsettings import UNSET
else:
    from sessionsettings import UNSET


# Capture the installed backend's contract before tests/applications replace clients.
_PARAMIKO_OPTIONS = frozenset(inspect.signature(paramiko.SSHClient.connect).parameters) - {'self', 'hostname'}
_EXTENSIONS = {'parent_key_filename', 'proxy_command', 'proxy_jump', 'ssh_config',
               'missing_host_key_policy', 'known_hosts_source'}
_REMOVED_NAMES = {'host': 'hostname', 'pkey_path': 'parent_key_filename',
                  'proxyCommand': 'proxy_command', 'proxyJump': 'proxy_jump',
                  'policy': 'missing_host_key_policy', 'known_hosts': 'known_hosts_source'}


def validate_connection_options(options):
    """Reject unknown/version-unsupported kwargs before files or connections open."""
    for name in options:
        if name not in _PARAMIKO_OPTIONS | {'parent_key_filename'}:
            candidates = _PARAMIKO_OPTIONS | _EXTENSIONS | {'hostname'}
            suggestion = ([_REMOVED_NAMES[name]] if name in _REMOVED_NAMES else
                          difflib.get_close_matches(name, sorted(candidates), n=1))
            hint = f"; did you mean '{suggestion[0]}'?" if suggestion else ''
            if name == 'key_path':
                hint = "; use 'key_filename' for local files or 'parent_key_filename' for caller-host files"
            raise TypeError(f"Unknown connect parameter '{name}'{hint}")


class _RawConfig(paramiko.SSHConfig):
    def _expand_variables(self, config, target_hostname):
        # Expansion must happen after explicit API overrides are applied.
        return config


def _expand(value, tokens):
    def substitute(match):
        token = match.group(0)
        if token not in tokens:
            raise ValueError(f'unsupported SSH config token: {token}')
        return str(tokens[token])
    return re.sub(r'%[%A-Za-z]', substitute, value)


def resolve_connection(hostname, *, username=None, port=None, ssh_config=None,
                       proxy_command=UNSET, proxy_jump=UNSET, **options):
    """Return effective connection options without opening connections or keys.

    None reads ~/.ssh/config if it exists; False disables config; a path is
    required to exist. Explicit arguments override config. Only local callers
    should opt into reading local config for an already nested SSH connection.
    """
    validate_connection_options(options)
    for name in ('pkey', 'key_filename', 'parent_key_filename', 'passphrase', 'sock'):
        if options.get(name, UNSET) is None:
            options.pop(name)
    host = hostname
    if not isinstance(host, str):
        raise TypeError('host must be str')
    if '@' in host:
        user, host = host.rsplit('@', 1)
        if username is None:
            username = user
    if not host or host.startswith('-') or any(c.isspace() or c == '\x00' for c in host):
        raise ValueError('host must be a nonempty hostname or address')
    alias = host
    config = {}
    path = None
    if ssh_config is not False:
        if ssh_config is not None and not isinstance(ssh_config, (str, os.PathLike)):
            raise TypeError('ssh_config must be a path, None, or False')
        path = os.path.expanduser(os.fspath(ssh_config) if ssh_config is not None else '~/.ssh/config')
        try:
            with open(path, encoding='utf-8') as stream:
                source = stream.read()
        except FileNotFoundError:
            if ssh_config is not None:
                raise
        else:
            # Paramiko can execute Match exec during lookup. Reject before parse.
            for line in source.splitlines():
                match = re.match(r'\s*([\w]+)(?:\s|=|$)', line)
                if match and match[1].lower() in ('match', 'include', 'canonicalizehostname'):
                    raise NotImplementedError(f'SSH config directive {match[1]} is not supported')
            parser = _RawConfig.from_text(source)
            config = parser.lookup(alias)
    supported = {'hostname', 'user', 'port', 'identityfile', 'proxycommand', 'proxyjump'}
    unsupported = sorted(set(config) - supported)
    if unsupported:
        warnings.warn('SSH config options not applied: ' + ', '.join(unsupported),
                      UserWarning, stacklevel=2)
    host = _expand(config.get('hostname', alias), {'%h': alias, '%n': alias, '%%': '%'})
    username = username if username is not None else config.get('user')
    if username is not None and (not isinstance(username, str) or not username
                                 or any(c.isspace() or c == '\x00' for c in username)):
        raise ValueError('username must be a nonempty string without whitespace')
    port = port if port is not None else int(config.get('port', 22))
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError('port must be an integer between 1 and 65535')
    if not host or host.startswith('-') or any(c.isspace() or c in '\x00%' for c in host):
        raise ValueError('resolved HostName must be a hostname or address')
    tokens = {'%%': '%', '%h': host, '%n': alias, '%p': port,
              '%r': username or getpass.getuser(), '%u': getpass.getuser(),
              '%d': os.path.expanduser('~')}
    if not any(key in options for key in ('key_filename', 'pkey', 'parent_key_filename')):
        keys = config.get('identityfile', [])
        if keys:
            options['key_filename'] = [os.path.expanduser(_expand(key, tokens)) for key in keys if key.lower() != 'none']

    explicit_proxy = proxy_command is not UNSET or proxy_jump is not UNSET
    command = None if proxy_command is UNSET else proxy_command
    jump = None if proxy_jump is UNSET else proxy_jump
    if not explicit_proxy:
        command, jump = config.get('proxycommand'), config.get('proxyjump')
    if command is not None and not isinstance(command, str):
        raise TypeError('proxy_command must be a string or None')
    if jump is not None and not isinstance(jump, str):
        raise TypeError('proxy_jump must be a string or None')
    if command and command.lower() == 'none':
        command = None
    if jump and jump.lower() == 'none':
        jump = None
    if command and jump:
        raise ValueError('ProxyCommand and ProxyJump cannot both be active; override one explicitly')
    if command:
        # Explicit proxy_command retains its historical verbatim semantics.
        options['proxy_command'] = command if explicit_proxy else _expand(command, tokens)
    elif jump:
        jumps = jump.split(',')
        if any(not item or any(c.isspace() or c in '\x00%' for c in item) for item in jumps):
            raise ValueError('invalid ProxyJump chain')
        endpoint = urlsplit('ssh://' + jumps[-1])
        if not endpoint.hostname or endpoint.hostname.startswith('-') or endpoint.password or endpoint.path or endpoint.query or endpoint.fragment:
            raise ValueError('ProxyJump must use [user@]host[:port]')
        # OpenSSH manages hop authentication; Paramiko still verifies the target.
        args = ['ssh', '-F', path if path and os.path.isfile(path) else os.devnull,
                '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
                '-W', f'[{host}]:{port}']
        if len(jumps) > 1:
            args.extend(['-J', ','.join(jumps[:-1])])
        if endpoint.port is not None:
            args.extend(['-p', str(endpoint.port)])
        if endpoint.username is not None:
            args.extend(['-l', endpoint.username])
        args.append(endpoint.hostname)
        options['proxy_command'] = shlex.join(args)
    return dict(options, hostname=host, username=username, port=port)
