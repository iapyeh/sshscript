---
title: "Session.connect()"
parent: "Core Session API"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
---

# Session.connect()

`Session.connect()` creates a connected child Session. Commands use the same
`exec_command()` method locally and remotely, and the connection closes when
its context exits.

## Connect to a host

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        stdout, stderr = remote.exec_command("hostname", shell=False)
        print(str(stdout).strip())

    with local.connect("ops@example.net", port=2222) as remote:
        remote.exec_command("uname -a", shell=False)
finally:
    local.close(strict=True)
```

The `user@host` form supplies both the username and host. Separate
`host="example.net"` and `username="ops"` arguments are also accepted.

## Authentication

Connection options not handled by SSHScript are passed to Paramiko's
`SSHClient.connect()`. Prefer an SSH agent or key authentication, and never
commit production secrets.

```python
import os
from sshscript import Session

local = Session()
try:
    with local.connect(
        "ops@example.net",
        key_filename=os.path.expanduser("~/.ssh/id_ed25519"),
    ) as remote:
        remote.exec_command("whoami", shell=False)
finally:
    local.close(strict=True)
```

For an interactive password:

```python
from getpass import getpass
from sshscript import Session

password = getpass("Password for ops@example.net: ")
local = Session()
try:
    with local.connect(
        "ops@example.net",
        password=password,
    ) as remote:
        remote.exec_command("uptime", shell=False)
finally:
    local.close(strict=True)
```

When `host` uses `user@host`, a second positional argument is accepted as the
password for compatibility. Prefer the explicit `password=` form in new code.

## Host-key verification

SSHScript loads system host keys and rejects unknown or changed host keys by
default. Add the server key to `known_hosts` before a normal connection.

Accepting a previously unknown key must be an explicit decision:

```python
import paramiko
from sshscript import Session

local = Session()
try:
    with local.connect(
        "ops@new-host.example",
        policy=paramiko.AutoAddPolicy(),
    ) as remote:
        remote.exec_command("hostname", shell=False)
finally:
    local.close(strict=True)
```

Use `AutoAddPolicy()` only in a trusted bootstrap environment where the new
server identity has been verified out of band. It is not the production
default. The legacy `policy=0` form is deprecated and now selects secure
default verification.

## Nested connections

Call `connect()` on an active remote Session to reach an internal host through
its SSH transport:

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@bastion.example.net") as bastion:
        with bastion.connect("db@db.internal") as database:
            database.exec_command("hostname", shell=False)
            database.exec_command(
                "systemctl is-active postgresql",
                shell=False,
            )
finally:
    local.close(strict=True)
```

For a nested connection, `pkey_path` refers to an RSA private key readable
from the currently connected parent host; SSHScript reads that file through
SFTP. Prefer Paramiko's normal key options for top-level connections.

## ProxyCommand and keepalives

A top-level connection may use `proxyCommand`:

```python
with local.connect(
    "ops@private.example.net",
    proxyCommand="ssh -W %h:%p jump.example.net",
) as remote:
    remote.exec_command("hostname", shell=False)
```

A nested connection already has a transport, so combining nested
`connect()` with `proxyCommand` is not supported.

SSH transports use a 60-second keepalive interval by default. Set the process
environment variable `KEEPALIVE_INTERVAL` to another integer number of
seconds, or to 0 to disable keepalives.

## Optional Dollar syntax

The equivalent `.spy` shorthand uses the current `$` Session:

```python
with $.connect("ops@example.net"):
    $hostname
    print($.stdout.strip())
```

Nested `$.connect()` blocks and the host-key policy follow the same Session
API behavior.

Last Updated: 2026-09-14 18:02:02
