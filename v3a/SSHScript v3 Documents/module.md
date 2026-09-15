---
title: "Module API"
parent: "SSHScript v3.1 Documentation"
nav_order: 1
---

# Module API

The regular Python `Session` API is SSHScript v3.1's primary interface. Use it
when automation belongs in an application, library, test suite, or ordinary
`.py` file. Dollar syntax is an optional `.spy` shorthand built on the same
session model.

## Create and close a Session

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

A new `Session` runs commands on localhost. Construction is side-effect free:
it does not globally patch Python imports, warnings, logging, or
`threading.Thread`.

`close()` is repeatable. By default cleanup failures are recorded in
`session.close_errors`; `close(strict=True)` raises when cleanup could not be
completed.

## Commands are strings

`Session.exec_command(command)` accepts exactly one non-empty `str`. Lists,
tuples, and other command types raise `TypeError`.

Build arguments with `shlex.join()` when shell expansion is not required:

```python
import shlex

arguments = ["python3", "-c", "print('hello world')"]
command = shlex.join(arguments)
stdout, stderr = session.exec_command(command, shell=False)
```

This keeps spaces and shell metacharacters inside individual arguments. Do
not pass `arguments` itself to `exec_command()`.

`Session.onedollar()` is a deprecated compatibility alias and follows the
same string-only rule. New Python code should call `exec_command()`.

## Shell selection

With the default `shell=None`, SSHScript inspects the final command string.
Plain commands run directly; pipelines, redirection, expansion, assignments,
and other shell syntax select a shell automatically.

```python
session.exec_command("uname -a", shell=False)
session.exec_command("printf 'alpha\\nbeta\\n' | grep beta")
session.exec_command("printf '%s\\n' \"$HOME\"", shell=True)
session.exec_command(
    '[[ -n "$BASH_VERSION" ]] && printf "%s\\n" "$BASH_VERSION"',
    shell="bash",
)
```

Use `shell=False` for safely quoted argument strings, `shell=True` to force
the POSIX shell, or `shell="bash"` only when a command needs Bash features.

## Results

Every command returns `(stdout, stderr)` and updates the Session's latest
result:

```python
stdout, stderr = session.exec_command(
    "python3 -c \"import sys; print('out'); "
    "sys.stderr.write('err\\n'); sys.exit(7)\""
)

print(str(stdout).strip())
print(str(stderr).strip())
print(session.exitcode)  # 7
```

The next command replaces `session.stdout`, `session.stderr`, and
`session.exitcode`, so keep values needed later in Python variables.

## Remote Sessions

`connect()` returns a child Session. The same `exec_command()` API then runs
on the selected host:

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

Connections can be nested for bastion-host workflows. See
[`Session.connect()`](Basic/connect) for authentication and host-key
verification.

## Script helpers

`sshscript.run_script(source)` runs in-memory Python or Dollar syntax in a
new local Session. `sshscript.run_file(path)` runs exactly one existing
regular Python or `.spy` file:

```python
import sshscript

status = sshscript.run_file("automation.spy")
```

Directories, globs, iterables, and multiple paths are not accepted. Compose
larger automation through ordinary Python imports or SSHScript include
syntax.

## Next steps

- Follow the [Module API Tutorial](tutorial).
- Learn [CLI and Environment](cli-and-environment).
- Review [Development and Testing](development-and-testing).
- Use the [Dollar Syntax Add-on](Basic/dollar) only when concise `.spy`
  notation is useful.

Last Updated: 2026-09-14 18:02:02
