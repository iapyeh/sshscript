---
title: "Connections, Authentication, and Bastions"
parent: "How-to Guides"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
---

# Connections, Authentication, and Bastions

> **Version scope:** The argv/CommandResult/check/config API is available in 3.1.5.
> Session settings and managed jobs/deadlines are features available in 4.0.1.
> Use the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/) to choose
> examples for your installed version.

`Session.connect()` creates a connected child Session. Commands use the same
`exec_command()` method locally and remotely, and the connection closes when
its context exits.

## Connect to a host

```python
from contextlib import closing
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        stdout, stderr, exitcode = remote.exec_command("hostname", shell=False)
        print(str(stdout).strip())

    with local.connect("ops@example.net", port=2222) as remote:
        remote.exec_command("uname -a", shell=False)
finally:
    local.close(strict=True)
```

The `user@host` form supplies both the username and host. Separate
`host="example.net"` and `username="ops"` arguments are also accepted.

## Reuse SSH config and preview settings

Local connections read `~/.ssh/config` if present. Supported settings are
`Host` patterns, `HostName`, `User`, `Port`, `IdentityFile`, `ProxyCommand`, and
`ProxyJump`. Explicit API arguments override config, which overrides defaults.
`port=None` means unspecified; `port=22` explicitly overrides a configured port.
Explicit `pkey`, `pkey_path`, or `key_filename` overrides identity files.

```text
Host production
    HostName server.example.net
    User deploy
    Port 2222
    IdentityFile ~/.ssh/deploy_key
    ProxyJump bastion.example.net
```

```python
from contextlib import closing
from sshscript import Session

settings = Session.resolve_connection("production")  # no connection or proxy
with closing(Session()) as local:
    with local.connect("production") as remote:
        result = remote.exec_command(["uname", "-s"], check=True)
        stdout, stderr, exitcode = result
```

`resolve_connection()` returns effective Paramiko arguments plus `proxyCommand`
when needed. It does no network operations. `ssh_config=False` disables config;
a file path selects a config file that must exist. Nested connections skip
local config unless an explicit file is supplied. `session.host` and saved
`result.host` use the resolved HostName, not the remote `hostname` command.

Identity paths and configured proxy commands expand `%h`, `%n`, `%p`, `%r`,
`%u`, `%d`, and `%%` after explicit overrides. Unknown tokens fail clearly.
`HostName` accepts `%h`, `%n`, and `%%`; `~` expands in identity paths.
Explicit `proxyCommand` keeps its verbatim behavior and does not expand tokens.
Use `proxyCommand=None` to disable configured proxies.

`Match`, `Include`, and hostname canonicalization are rejected before lookup.
Other unapplied settings produce a warning; this is a subset of OpenSSH config,
not full equivalence. Alternate known-hosts files and identity-agent settings
are not imported into Paramiko. Existing target host-key verification remains
in force. Config is trusted local input: connecting can execute proxy programs.

## ProxyJump

Use config or an explicit `proxyJump="user@bastion:2222"`. Comma-separated
chains and bracketed IPv6 hosts are accepted. SSHScript uses the local `ssh`
executable to forward to the target, and Paramiko authenticates and verifies
the target connection. The forwarding command uses batch authentication and
strict host-key checking; provision verified keys and noninteractive jump-host
authentication beforehand. OpenSSH manages earlier hops in a chain according
to its SSH configuration. Custom config files are passed to `ssh` as well.

When ProxyCommand and ProxyJump are both active, choose one explicitly or
remove the conflict; this implementation does not reproduce OpenSSH's
first-proxy-wins behavior. Nested Sessions already tunnel through their parent
and reject additional proxy options. Proxy connections default connect,
banner, and authentication timeouts to 30 seconds, unless overridden.

## Authentication

Connection options not handled by SSHScript are passed to Paramiko's
`SSHClient.connect()`. Prefer an SSH agent or key authentication, and never
commit production secrets.

```python
import os
from contextlib import closing
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
from contextlib import closing
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
from contextlib import closing
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

<a id="default-host-key-policy-unreleased-source-api"></a>

## Default host-key policy (4.0 source API)

In the development source, configure a Session once instead of passing `policy`
to every connection:

```python
from contextlib import closing
import paramiko
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    local.set(policy=paramiko.AutoAddPolicy())
    with local.connect("ops@first.example.net") as first:
        first.exec_command(["hostname"], check=True)
    with local.connect("ops@second.example.net") as second:
        second.exec_command(["hostname"], check=True)
    with local.connect("ops@verified.example.net", policy=None) as verified:
        verified.exec_command(["hostname"], check=True)
```

Use AutoAddPolicy only under the bootstrap conditions described above. The
`policy` setting defaults to `None` and accepts a Paramiko `MissingHostKeyPolicy`
instance or subclass. `local.policy = ...` and `local.get("policy")` access the
same setting. In `.spy`, use `$.set(policy=paramiko.AutoAddPolicy())` and
`$.get("policy")`.

Omitting the connect argument uses the Session setting. An explicit policy
wins for that connection; explicit `None` uses Paramiko's default RejectPolicy.
Child Sessions snapshot the parent's settings, including policy, independently
of a per-connection override. Nested connections use the child's setting.
Changing a setting affects future connections, not existing clients. The
settings dictionary is copied, but the policy object is shared; custom policies
with mutable state must support reuse.

This setting is not available in published 3.1.5. On that version, keep using
`connect(policy=...)` for each connection.

## Nested connections

Call `connect()` on an active remote Session to reach an internal host through
its SSH transport:

```python
from contextlib import closing
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
    proxyCommand="ssh -o StrictHostKeyChecking=yes -W private.example.net:22 jump.example.net",
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

Last Updated: 2026-10-08 23:48:09
