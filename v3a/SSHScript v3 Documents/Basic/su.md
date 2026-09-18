---
title: "Using Session.su()"
parent: "How-to Guides"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 4
---

# Using Session.su()

`Session.su()` opens an interactive `su` context as another Unix account. It
works on localhost and on a connected child Session.

## Switch account for a block

```python
from getpass import getpass
from sshscript import Session

password = getpass("Password for deploy: ")
session = Session()
try:
    with session.su("deploy", password=password) as deploy:
        deploy.exec_command("whoami")
        deploy.expect("deploy")
        print(str(deploy.stdout))
finally:
    session.close(strict=True)
```

When the block ends, SSHScript leaves the `su` console and restores the
previous identity. Whether a password is required depends on the host's PAM
and `su` configuration.

## Use it over SSH

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        with remote.su("deploy", password=password) as deploy:
            deploy.exec_command("whoami")
            deploy.exec_command("cd /srv/deploy; ./maintenance.sh")
finally:
    local.close(strict=True)
```

## Options

`Session.su(username, password=None, expect=None, initials=None,
shell=True, login=True, get_pty=True)`

| Option | Purpose |
| --- | --- |
| `username` | Account to enter. |
| `password` | Value sent when `su` prompts. |
| `expect` | Prompt pattern for a non-standard environment. |
| `initials` | A string or iterable of initial commands. |
| `login` | Use login-style account switching; default `True`. |
| `shell` | Use the normal interactive base shell; default `True`. |
| `get_pty` | Request a pseudo-terminal; default `True`. |

Keep `get_pty=True` when the host requires a TTY. Set `expect=` only when the
normal password prompt cannot be detected.

## Combine with sudo

```python
with session.su("deploy", password=deploy_password) as deploy:
    with deploy.sudo(password=deploy_password) as root:
        root.exec_command("whoami")
```

The sudo password, if required, belongs to the account currently running
`sudo`.

## Optional Dollar syntax

```python
with $.su("deploy", password=deploy_password):
    $whoami
    $id
```

Never hard-code passwords in Python or `.spy` files. Use `getpass`, a secret
manager, or narrowly scoped policy-based access.

Last Updated: 2026-09-18 15:58:44
