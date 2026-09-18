---
title: "Using Session.sudo()"
parent: "How-to Guides"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
---

# Using Session.sudo()

`Session.sudo()` opens an interactive `sudo` context for a block. It handles
the password prompt and restores the preceding Session context when the block
ends.

## Run commands as root

```python
from getpass import getpass
from sshscript import Session

password = getpass("sudo password: ")
session = Session()
try:
    with session.sudo(password=password) as root:
        root.exec_command("whoami")
        root.expect("root")
        root.exec_command("systemctl restart nginx")
finally:
    session.close(strict=True)
```

For an account permitted to run the required commands without a password:

```python
with session.sudo() as root:
    root.exec_command("id -u")
```

The host's `sudoers` policy controls the result. SSHScript does not bypass
that policy.

## Run as a named account

```python
with session.sudo(
    password=password,
    username="www-data",
) as web:
    web.exec_command("whoami")
    web.exec_command("touch /var/www/example/cache-warmed")
```

The password, if requested, is normally that of the current account rather
than the target account.

## Remote use

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        with remote.sudo(password=password) as root:
            root.exec_command("systemctl status nginx")
            root.exec_command("journalctl -u nginx -n 20")
finally:
    local.close(strict=True)
```

## Options

`Session.sudo(password=None, username=None, expect=None, initials=None,
shell=True, login=True, get_pty=True)`

| Option | Purpose |
| --- | --- |
| `password` | Value sent when `sudo` prompts. |
| `username` | Permitted target account; the default is root. |
| `expect` | Prompt pattern for a non-standard environment. |
| `initials` | A string or iterable of initial commands. |
| `login` | Request login-style account handling; default `True`. |
| `shell` | Use the normal interactive base shell; default `True`. |
| `get_pty` | Request a pseudo-terminal; default `True`. |

Interactive privilege systems often require a pseudo-terminal. Keep
`get_pty=True` unless the host is known to work without one.

## Optional Dollar syntax

```python
with $.connect("ops@example.net"):
    with $.sudo(password=password):
        $systemctl status nginx
```

Never hard-code production passwords. Prefer narrowly scoped `sudoers` rules,
SSH keys, and a secret manager or `getpass` for interactive use.

Last Updated: 2026-09-18 15:58:44
