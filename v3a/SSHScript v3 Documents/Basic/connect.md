---
title: "$.connect"
parent: "Basic"
nav_order: 4
---

# $.connect

`$.connect` opens an SSH session and makes it current for a `with` block.
Commands written with [`$`](dollar) in that block execute on the remote host.
Leaving the block closes the connection and restores the previous session.

## Connect to a host

```python
with $.connect("ops@example.net"):
    $hostname
    print($.stdout.strip())

with $.connect("ops@example.net", port=2222):
    $uname -a
```

## Authentication

SSHScript forwards normal connection arguments to Paramiko. Prefer an SSH
agent or key authentication, and do not store production secrets in scripts.

```python
# Private key located on the local machine.
with $.connect("ops@example.net", pkey_path="/Users/me/.ssh/id_ed25519"):
    $whoami
```

```python
from getpass import getpass

password = getpass("Password for ops@example.net: ")
with $.connect("ops@example.net", password=password):
    $uptime
```

When the host uses `user@host`, the second positional argument is accepted as
the password for compatibility. For new scripts, `password=password` is
clearer.

## Nested connections

Call `$.connect` inside an active connection to reach an internal host
through the current SSH transport:

```python
with $.connect("ops@bastion.example.net"):
    $hostname
    with $.connect("db@db.internal"):
        $hostname
        $systemctl is-active postgresql
```

For a nested connection, `pkey_path` refers to a key reachable from the
currently active host. This supports a bastion that holds the internal host's
key.

At the top level, `proxyCommand` may be used:

```python
with $.connect(
    "ops@private.example.net",
    proxyCommand="ssh -W %h:%p jump.example.net",
):
    $hostname
```

Nested connections already have a transport, so `proxyCommand` is not
supported inside a nested `$.connect` block.

## Host keys

By default, SSHScript uses Paramiko's `AutoAddPolicy`, which accepts an
unknown host key. Production automation should choose and manage host-key
verification according to its security policy:

```python
import paramiko

with $.connect("ops@example.net", policy=paramiko.RejectPolicy()):
    $hostname
```

## Combining contexts

```python
with $.connect("ops@example.net"):
    $df -h | tail -n +2
    with $.sudo():
        $systemctl status nginx
```

See [`$.sudo`](sudo) and [`$.su`](su) for privilege changes.
