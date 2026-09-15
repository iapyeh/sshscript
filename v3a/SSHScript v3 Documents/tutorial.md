---
title: "Module API Tutorial (EN)"
parent: "SSHScript v3.1 Documentation"
nav_order: 2
---

# Module API Tutorial (EN)

This tutorial introduces SSHScript v3.1 through its primary Python
`Session` API. The optional Dollar syntax is shown only after the module
workflow.

## Install SSHScript

SSHScript requires Python 3.9 or newer:

```sh
python3 -m pip install sshscript
```

## Execute a local command

```python
from sshscript import Session

session = Session()
try:
    stdout, stderr = session.exec_command("hostname", shell=False)
    print(str(stdout).strip())
    print(session.exitcode)
finally:
    session.close(strict=True)
```

The latest command result is available as `session.stdout`,
`session.stderr`, and `session.exitcode`. Each new command replaces those
properties.

## Build a command safely

`exec_command()` accepts exactly one non-empty string. Use `shlex.join()` to
quote a dynamic argument list, then force direct execution:

```python
import shlex
from sshscript import Session

arguments = ["printf", "%s\n", "hello world"]
command = shlex.join(arguments)

session = Session()
try:
    session.exec_command(command, shell=False)
    print(str(session.stdout), end="")
finally:
    session.close(strict=True)
```

Do not pass `arguments` directly; list and tuple commands raise `TypeError`.

## Use shell features deliberately

With `shell=None`, the default, SSHScript automatically detects pipelines,
redirection, expansion, and other shell syntax.

```python
session.exec_command("printf 'alpha\\nbeta\\n' | grep beta")
```

Set `shell=False` for direct execution, `shell=True` to force the POSIX
shell, or `shell="bash"` for a Bash-only command.

## Connect to a remote host

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        stdout, stderr = remote.exec_command("hostname", shell=False)
        print(str(stdout).strip())
finally:
    local.close(strict=True)
```

SSHScript loads system host keys and rejects unknown or changed host keys by
default. Add the server key to `known_hosts` before connecting. See
[`Session.connect()`](Basic/connect) for authentication, trusted bootstrap,
and nested connections.

## Compose privileged contexts

The object returned by `connect()` owns the remote command context:

```python
from getpass import getpass
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        password = getpass("sudo password: ")
        with remote.sudo(password=password) as root:
            root.exec_command("id -u")
            print(str(root.stdout).strip())
finally:
    local.close(strict=True)
```

The inner context exits the privileged shell; the outer context closes the
remote Session. Host policy still controls whether `sudo` is permitted.

## Automate an interactive program

```python
from sshscript import Session

session = Session()
try:
    with session.enter(
        "python3",
        prompt=">>>",
        exit="quit()",
    ) as console:
        console.input("print('hello from SSHScript')")
        console.expect("hello from SSHScript")
finally:
    session.close(strict=True)
```

Use `enter()` for REPLs, database tools, password prompts, and long-running
programs. See [`Session.enter()`](Advanced/enter) for prompt matching and
safe password input.

## Transfer files

File transfer uses the active connected Session:

```python
import os
from sshscript import Session

os.makedirs("./reports", exist_ok=True)
local = Session()
try:
    with local.connect("ops@example.net") as remote:
        remote.upload(
            "./release.tar.gz",
            "/var/tmp/releases/",
            makedirs=True,
        )
        remote.download(
            "/var/tmp/report.txt",
            "./reports/",
        )
finally:
    local.close(strict=True)
```

See [`Session.upload()` and `Session.download()`](Advanced/file-transfer)
for path and overwrite behavior.

## Run a `.spy` file

The CLI runs exactly one regular Python or `.spy` file:

```sh
sshscript maintenance.spy
```

Larger programs use imports or include syntax rather than multiple CLI
paths. See [CLI and Environment](cli-and-environment).

## Optional Dollar syntax

Inside a `.spy` file, the same session model has a concise notation:

```python
with $.connect("ops@example.net"):
    $hostname
    print($.stdout.strip())
```

In v3.1, one `$` handles both direct commands and shell features. The former
`$$` form is deprecated. See [Dollar Syntax Add-on](Basic/dollar) if this
notation suits the project.

Last Updated: 2026-09-14 18:02:02
