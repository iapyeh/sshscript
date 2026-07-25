---
title: $.enter
parent: Advanced
nav_order: 1
updated:
---

# $.enter

`$.enter` opens an interactive program in the current SSHScript session.
Use it for REPLs, database clients, password-driven programs, and commands
that keep running while they receive input. It works locally, over SSH, and
inside [`$.su`](../Basic/su) or [`$.sudo`](../Basic/sudo) contexts.

## Enter an interactive program

Pass the command and, when known, its prompt:

```python
with $.enter("python3", prompt=">>>", exit=chr(4)):
    $.input("print('hello from SSHScript')")
    $.expect("hello from SSHScript")
    print($.stdout)
```

Within the block, `$.input(text)` sends one line of input. `$.expect()`
waits until text appears in output. The `exit=chr(4)` value sends Ctrl-D
when the block ends, which exits the Python interpreter.

The `$` shorthand also sends a line while an `$.enter` context is active:

```python
with $.enter("python3", prompt=">>>", exit="quit()"):
    $print(2 + 3)
    $.expect("5")
```

Use `$.input()` when making interactive input explicit improves readability;
use the dollar shorthand when it makes a sequence of console commands easier
to read.

## Wait for a prompt or result

The command can return a console object. This is useful when the interactive
steps should be visually separated:

```python
with $.enter("python3", prompt=">>>", exit="quit()") as console:
    console("import datetime")
    console("print('TIME-OK', datetime.datetime.now().year)")
    console.expect("TIME-OK")
    print(console.stdout)
```

`$.expect(pattern, timeout=None, stdout=True, stderr=True, silent=False)`
checks stdout and stderr by default. Pass `stderr=False` when only stdout is
relevant:

```python
with $.enter("python3 -i", exit="quit()", get_pty=False):
    $.expect("python")
    $.input("print('READY')")
    $.expect("READY", stderr=False)
```

If a program's prompt changes after it starts, set it explicitly:

```python
with $.enter("sudo python3", expect="password", password=password):
    $.set_prompt(">>>")
    $.input("print('running as the selected account')")
    $.expect("selected account")
    $.input("quit()")
```

## Handle a login or password prompt

`expect=` and `password=` let SSHScript answer an initial prompt before
the normal interactive work begins:

```python
from getpass import getpass

password = getpass("sudo password: ")
with $.enter(
    "sudo python3",
    expect="password",
    password=password,
    prompt=">>>",
    exit="quit()",
):
    $.input("print('privileged Python')")
    $.expect("privileged Python")
```

Do not hard-code secrets in a `.spy` file. Use `getpass` for an interactive
script or retrieve the secret from the deployment environment's secret
manager.

## Supply a password to mysqldump

Some commands are not interactive shells, but still pause for a password.
For example, `mysqldump -p` reads its password from the terminal after the
command has started. Use `$.enter` to wait for that prompt before providing
the password:

```python
from getpass import getpass

database_password = getpass("MySQL password: ")
remote_dump = "/tmp/application-backup.sql"

with $.connect("backup@example.net"):
    with $.enter(
        f"mysqldump -u backup -p --all-databases > {remote_dump}"
    ):
        $.expect("password")
        $.input(database_password)

    $f'test -s {remote_dump}'
    assert $.exitcode == 0
    $.download(remote_dump, "./downloads/")
```

The command includes shell redirection, so SSHScript runs it in the shell
context created for `$.enter`. `mysqldump` finishes after receiving the
password, therefore this example does not need `exit=`; leaving the block
waits for the command to finish. Check the resulting file before downloading
or restoring it, and remove the remote staging file when it is no longer
needed.

Use a specific prompt pattern if the MySQL client has been configured with a
different language or customised prompt. Keep the password in a short-lived
variable and never put it on the command line, where it can be visible in
process listings or shell history.

## End the program deliberately

Choose `exit=` based on the program:

| Value | Typical use |
| --- | --- |
| `exit="quit()"` | Python or another REPL with a quit command |
| `exit=chr(4)` | Ctrl-D / EOF, commonly for Python and Unix consoles |
| `exit=chr(3)` | Ctrl-C, for a process such as `tcpdump` or `tail -F` |
| `exit=None` | A command that finishes on its own |

For continuously producing output, combine `$.enter` with
[`Looping Output`](looping-output):

```python
with $.enter("journalctl -f -u nginx", exit=chr(3)):
    for line in $.stdout(30):
        if "error" in line.lower():
            print(line, end="")
```

## PTY and shell settings

The full form is:

```python
$.enter(
    command,
    expect=None,
    password=None,
    exit=None,
    shell=True,
    get_pty=True,
    prompt=None,
)
```

`shell=True` and `get_pty=True` are the defaults. A shell and a
pseudo-terminal make most interactive applications behave as they do in a
human SSH session. Set `get_pty=False` only when the application works
without a terminal and a PTY causes a problem.

## Nesting with remote and privileged sessions

Interactive programs retain the active connection and identity:

```python
with $.connect("ops@example.net"):
    with $.sudo(password=password):
        with $.enter("python3", prompt=">>>", exit=chr(4)):
            $.input("import os; print(os.getuid())")
            $.expect("0")
```

When the inner block exits, the script returns to the preceding `sudo`
session; when that block exits, it returns to the original SSH login session.

Last Updated: 2026-07-25 16:59:40
