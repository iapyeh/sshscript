---
title: "SSHScript v3.1"
nav_exclude: true
---

# SSHScript v3.1

SSHScript brings local commands, SSH automation, and Python control flow into
one programming model. Its primary interface is the regular Python `Session`
API, while the optional Dollar syntax offers concise notation for standalone
`.spy` scripts.

## Why SSHScript?

Use the same Session model to run a command on localhost, connect to a remote
host, enter a privileged or interactive context, transfer files, and return
cleanly through nested context managers. Python remains available for data
processing, branching, exceptions, testing, and integration with existing
applications.

SSHScript v3.1 emphasizes predictable and secure automation:

- commands are explicit non-empty strings;
- dynamic argument lists can be safely assembled with `shlex.join()`;
- SSH host keys are verified by default; and
- imports, threads, and script execution remain scoped instead of changing
  process-wide Python behavior.

## Installation

SSHScript requires Python 3.9 or newer:

```sh
python3 -m pip install sshscript
```

Upgrade an existing installation with:

```sh
python3 -m pip install --upgrade sshscript
```

## First command

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
accepted; use `shlex.join()` when building a direct command from arguments.

## Continue learning

Begin with the
[Module API Tutorial](SSHScript%20v3%20Documents/tutorial/), then use the
[SSHScript v3.1 Documentation](SSHScript%20v3%20Documents/) sidebar as the
technical reference.

The [Core Session API](SSHScript%20v3%20Documents/Basic/) covers connections
and privilege contexts. The
[Advanced Session API](SSHScript%20v3%20Documents/Advanced/) covers
interactive programs, transfers, streaming output, and threading. Use the
[Dollar Syntax Add-on](SSHScript%20v3%20Documents/Basic/dollar/) only when its
`.spy` notation suits the project.

For installation problems, see
[Installation Troubleshooting](SSHScript%20v3%20Documents/troubleshooting-installation/).
Practical scenarios are collected in the
[Example Gallery](Example%20Gallery/).

## Project status

SSHScript v3.1 is beta software. Run the credential-free release gate before
deployment and validate real SSH behavior in an isolated test environment
before production rollout. SSHScript is released under the MIT License.

Last Updated: 2026-09-15 09:40:34
