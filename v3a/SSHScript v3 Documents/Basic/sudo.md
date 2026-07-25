---
title: "$.sudo"
parent: "Basic"
nav_order: 3
---

# $.sudo

`$.sudo` starts an interactive `sudo` session for a `with` block. It
handles the password prompt and leaves the elevated console when the block
finishes.

## Run commands as root

```python
from getpass import getpass

password = getpass("sudo password: ")
with $.sudo(password=password):
    $whoami
    assert $.stdout.strip() == "root"
    $systemctl restart nginx
```

For an account allowed to run the required commands without a password:

```python
with $.sudo():
    $id -u
```

The host's `sudoers` policy controls the result. SSHScript cannot bypass
that policy.

## Run as a named account

```python
with $.sudo(password=password, username="www-data"):
    $whoami
    $touch /var/www/example/cache-warmed
```

The password, if requested, is normally that of the current account, not the
target account.

## Remote use

```python
from getpass import getpass

with $.connect("ops@example.net"):
    password = getpass("sudo password on example.net: ")
    with $.sudo(password=password):
        $systemctl status nginx
        $journalctl -u nginx -n 20
```

The inner block returns to the remote login account; the outer block then
returns to the local session.

## Options

`$.sudo(password=None, username=None, expect=None, initials=None,
shell=True, login=True, get_pty=True)`

| Option | Purpose |
| --- | --- |
| `password` | Value sent when sudo prompts. |
| `username` | Permitted target account. |
| `expect` | Prompt text for a non-standard sudo prompt. |
| `initials` | Initial input to send after entering the console. |
| `login` | Request login-style account handling; default `True`. |
| `shell` | Use the normal interactive shell; default `True`. |
| `get_pty` | Request a pseudo-terminal; default `True`. |

Interactive privilege systems often require a pseudo-terminal. It is enabled
by default; retain `get_pty=True` if the host enforces a TTY requirement.
Use `expect=` only for customised prompts.

## Combine with su

```python
with $.su("deploy", password=deploy_password):
    with $.sudo(password=deploy_password):
        $whoami
```

Here sudo authenticates as `deploy`, because it is the active account. See
[`$.su`](su) for changing identity before elevation.

## Security

Never hard-code production passwords. Prefer narrowly scoped `sudoers`
rules, SSH keys, and a secret manager or `getpass` for interactive use.

Last Updated: 2026-07-25 16:59:40
