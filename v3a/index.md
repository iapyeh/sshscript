---
title: "SSHScript v3.1"
nav_exclude: true
---

# SSHScript v3.1

SSHScript is a Python automation library and `.spy` script runner for
executing commands locally or over SSH. Its primary interface is the regular
Python `Session` API; the optional Dollar syntax provides a compact notation
for standalone automation scripts.

## Why SSHScript?

SSHScript keeps command execution, SSH connections, privilege changes,
interactive programs, file transfer, and Python control flow in one
programming model. The same `Session` code can begin on localhost, enter a
remote host, and return safely through nested context managers.

Version 3.1 also makes automation behavior more explicit:

- commands are non-empty strings, so dynamic argument lists can be quoted
  deliberately with `shlex.join()`;
- SSH host keys are verified by default;
- script execution and `.spy` imports are scoped instead of changing
  process-wide Python behavior; and
- credential-free tests cover the public module API and optional Dollar
  syntax.

## Installation

SSHScript requires Python 3.9 or newer.

```sh
python3 -m pip install sshscript
```

Upgrade an existing installation with:

```sh
python3 -m pip install --upgrade sshscript
```

## Quick start

```python
import shlex
from sshscript import Session

session = Session()
try:
    stdout, stderr = session.exec_command("uname -a", shell=False)
    print(str(stdout).strip())
    print(session.exitcode)

    arguments = ["printf", "%s\n", "hello world"]
    session.exec_command(shlex.join(arguments), shell=False)
finally:
    session.close(strict=True)
```

`Session.exec_command()` accepts one command string. Lists and tuples are not
accepted; use `shlex.join()` when assembling a command from arguments.

## Documentation

Start with the [Module API tutorial](SSHScript%20v3%20Documents/tutorial/),
then use the complete
[SSHScript v3.1 documentation](SSHScript%20v3%20Documents/) as a reference.
The [Dollar Syntax add-on](SSHScript%20v3%20Documents/Basic/dollar/) is
available for teams that prefer `.spy` files.

Practical scenarios are collected in the
[Example Gallery](Example%20Gallery/).

## Project status

SSHScript v3.1 is beta software. Run the credential-free release gate before
deployment and validate real SSH behavior in an isolated environment before
production rollout. SSHScript is released under the MIT License.

Last Updated: 2026-09-14 18:02:02
