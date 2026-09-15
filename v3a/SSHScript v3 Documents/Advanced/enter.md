---
title: "Session.enter()"
parent: "Advanced Session API"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
---

# Session.enter()

`Session.enter()` opens an interactive program in the current Session. Use it
for REPLs, database clients, password-driven commands, and long-running
programs that receive input after they start. It works locally, over SSH, and
inside `su()` or `sudo()` contexts.

## Enter an interactive program

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
        print(str(console.stdout))
finally:
    session.close(strict=True)
```

`input(text)` sends a line. `expect(pattern)` waits for matching output.
`exit=` specifies what SSHScript sends when the context ends.

The full Session signature is:

```python
session.enter(
    command,
    expect=None,
    password=None,
    exit=None,
    shell=True,
    get_pty=True,
    prompt=None,
)
```

`shell=True` and `get_pty=True` make most interactive applications behave as
they do in a terminal. Set `get_pty=False` only when the application works
without a terminal and a PTY causes a problem.

## Wait for prompts and results

```python
with session.enter(
    "python3 -i",
    exit="quit()",
    get_pty=False,
) as console:
    console.expect("python")
    console.input("print('READY')")
    console.expect("READY", stderr=False)
```

`expect(pattern, timeout=None, stdout=True, stderr=True, silent=False)` checks
stdout and stderr by default. Disable one stream when a match must come from
the other.

If a program changes its prompt after starting:

```python
with session.enter("python3", exit="quit()") as console:
    console.set_prompt(">>>")
    console.input("print('prompt set')")
    console.expect("prompt set")
```

## Answer an initial password prompt

`expect=` and `password=` can handle a prompt during context setup:

```python
from getpass import getpass

password = getpass("sudo password: ")
with session.enter(
    "sudo python3",
    expect="password",
    password=password,
    prompt=">>>",
    exit="quit()",
) as console:
    console.input("print('privileged Python')")
    console.expect("privileged Python")
```

Keep secrets out of command arguments and source files. Use `getpass` for an
interactive run or retrieve the secret from the deployment environment's
secret manager.

## Supply a password to `mysqldump`

Some commands are not interactive shells but still stop for terminal input.
For example, `mysqldump -p` asks for its password only after the process has
started. `enter()` can wait for that prompt and send the password without
placing it on the command line.

```python
import os
import shlex
from getpass import getpass
from sshscript import Session

database_password = getpass("MySQL password: ")
remote_dump = "/tmp/application-backup.sql"
os.makedirs("./downloads", exist_ok=True)
dump_command = (
    "mysqldump -u backup -p --all-databases > "
    + shlex.quote(remote_dump)
)

local = Session()
try:
    with local.connect("backup@example.net") as remote:
        with remote.enter(dump_command) as process:
            process.expect("password")
            process.input(database_password)

        remote.exec_command(
            "test -s " + shlex.quote(remote_dump),
            shell=True,
        )
        if remote.exitcode != 0:
            raise RuntimeError("mysqldump did not create a non-empty file")

        remote.download(remote_dump, "./downloads/")
finally:
    local.close(strict=True)
```

The redirection requires shell mode, which is the default for `enter()`.
`mysqldump` finishes after receiving the password, so this case does not need
an `exit=` action. Verify the file before downloading or restoring it, remove
the remote staging file when finished, and use a more specific prompt pattern
when the client has localized output.

## End the program deliberately

| Value | Typical use |
| --- | --- |
| `exit="quit()"` | Python or another REPL with a quit command |
| `exit=chr(4)` | Ctrl-D / EOF for Python and Unix consoles |
| `exit=chr(3)` | Ctrl-C for `tail -F`, `tcpdump`, or similar programs |
| `exit=None` | A command that finishes on its own |

For a continuous producer, combine `enter()` with
[Streaming Output](looping-output).

## Nest remote and privileged Sessions

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        with remote.sudo(password=password) as root:
            with root.enter(
                "python3",
                prompt=">>>",
                exit=chr(4),
            ) as console:
                console.input("import os; print(os.getuid())")
                console.expect("0")
finally:
    local.close(strict=True)
```

Each inner context returns to its predecessor when it exits.

## Optional Dollar syntax

Inside a `.spy` file:

```python
with $.enter("python3", prompt=">>>", exit="quit()"):
    $.input("print(2 + 3)")
    $.expect("5")
```

The shorthand `$print(2 + 3)` also sends a line while `$.enter()` is active.
Use `$.input()` when explicit interaction is easier to maintain.

Last Updated: 2026-09-14 18:02:02
