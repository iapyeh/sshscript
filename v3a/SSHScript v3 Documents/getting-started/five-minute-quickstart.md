---
title: "5-Minute Quickstart"
parent: "Getting Started"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
permalink: /v3a/getting-started/quickstart/
---

# 5-Minute Quickstart

This quickstart proves the v3.1 Module API on localhost. It requires no SSH
server, account, key, password, or network connection.

## Before you begin

Complete [Installation and Verification](../installation-and-verification/).
Both verification commands must report `3.1.4` from the intended environment.

## Create a script

Save the following as `quickstart.py`:

```python
import shlex
import sys

from sshscript import Session


session = Session()
try:
    command = shlex.join([
        sys.executable,
        "-c",
        "print('hello from SSHScript')",
    ])

    stdout, stderr = session.exec_command(command, shell=False)

    print("stdout:", str(stdout).strip())
    print("stderr:", repr(str(stderr)))
    print("exit code:", session.exitcode)
finally:
    session.close(strict=True)
```

Run it with the same Python environment used for installation:

```sh
python3 quickstart.py
```

Expected output:

```text
stdout: hello from SSHScript
stderr: ''
exit code: 0
```

You have now created a local `Session`, executed one command, captured both
output streams, inspected the process status, and closed every resource.

## What the example establishes

`Session.exec_command()` accepts one non-empty command string and returns
`(stdout, stderr)`. It also updates the Session's latest result:

```python
session.stdout
session.stderr
session.exitcode
```

The output objects are live, string-like buffers. Use `str(stdout)` or
`str(stderr)` when you need a stable string snapshot. The next command
replaces the Session's latest result, so retain returned values that must be
used later.

The example begins with an argument list because dynamic arguments are often
safer to reason about in that form. `shlex.join()` converts the arguments to
one correctly quoted string. On this local Session, `shell=False` executes
the resulting argument vector without a shell. Never pass the list itself to
`exec_command()`; v3.1 raises `TypeError`.

## Use a shell feature deliberately

Add the following before the `finally` block:

```python
    stdout, stderr = session.exec_command(
        "printf 'alpha\\nbeta\\n' | grep beta"
    )
    print("pipeline:", str(stdout).strip())
```

Expected additional output:

```text
pipeline: beta
```

The default `shell=None` detects that the pipeline requires a shell. For code
that does not require expansion, redirection, pipelines, or other shell
syntax, prefer a string assembled with `shlex.join()` and `shell=False`.

## Handle a nonzero command status

A command that starts and exits with a nonzero status does not normally raise
an exception. Check `exitcode` explicitly:

```python
    failing_command = shlex.join([
        sys.executable,
        "-c",
        "import sys; sys.exit(7)",
    ])
    stdout, stderr = session.exec_command(
        failing_command,
        shell=False,
    )

    if session.exitcode != 0:
        print("command failed with:", session.exitcode)
```

Expected additional output:

```text
command failed with: 7
```

This differs from an API or operational failure. Invalid arguments, a local
`shell=False` startup failure such as a missing executable, local command
timeout, and SSH authentication or transport failures raise exceptions. In
local shell mode or on a remote Session, a missing executable is normally
reported as a nonzero result—commonly exit status `127` with diagnostic
stderr—instead. Handle both exceptions and nonzero command results.

## Next steps

- [Your First SSH Connection](../first-ssh-connection/) securely moves the same
  Session model to an SSH host.
- [Module API Tutorial]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/tutorial/)
  continues through connections,
  privilege contexts, interactive programs, and transfers.
- [Session and Console API Reference](../../reference/session-and-console-api/)
  defines the supported core contract.
- [Failure Model and Production Checklist](../../security-and-operations/failure-model-and-production-checklist/)
  explains how to turn examples into operational code.

Last Updated: 2026-09-25 16:37:52
