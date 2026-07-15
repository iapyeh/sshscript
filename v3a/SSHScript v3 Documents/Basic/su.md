---
title: "$.su"
parent: "Basic"
nav_order: 2
---

# $.su

`$.su` starts an interactive `su` session and executes a `with` block as
another Unix account. It works locally and inside [`$.connect`](connect).

## Switch account for a block

```python
from getpass import getpass

deploy_password = getpass("Password for deploy: ")
with $.su("deploy", password=deploy_password):
    $whoami
    assert $.stdout.strip() == "deploy"
    $id
```

When the block ends, SSHScript leaves the `su` console and restores the
previous identity. Use `$.su` rather than issuing a separate `su` command:
it handles the interactive prompt and cleanup for the whole block.

## Use it over SSH

```python
with $.connect("ops@example.net"):
    $whoami
    with $.su("deploy", password=deploy_password):
        $whoami
        $cd /srv/deploy; ./maintenance.sh
```

Whether a password is needed depends on the remote host's PAM and `su`
configuration.

## Options

`$.su(username, password=None, expect=None, initials=None, shell=True,
login=True, get_pty=True)`

| Option | Purpose |
| --- | --- |
| `password` | Value sent when `su` prompts. |
| `expect` | Prompt text for a non-standard environment. |
| `initials` | Initial input to send after entering the console. |
| `login` | Use login-style account switching; default `True`. |
| `shell` | Use the normal interactive shell; default `True`. |
| `get_pty` | Request a pseudo-terminal; default `True`. |

The defaults are right for most systems. Keep or explicitly set
`get_pty=True` when the host requires a TTY. Use `expect=` only if a
customised prompt is not detected normally.

## Combine with sudo

```python
with $.su("deploy", password=deploy_password):
    $whoami
    with $.sudo(password=deploy_password):
        $whoami  # normally root
```

The sudo password, if required, belongs to the account currently running
`sudo`. See [`$.sudo`](sudo) for target-account options.

## Security

Never commit passwords to a `.spy` file. Use `getpass`, a secret manager,
or policy- and key-based access, and grant only the privileges required.
