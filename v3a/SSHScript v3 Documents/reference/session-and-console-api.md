---
title: "Session and Console API Reference"
parent: "Reference"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
permalink: /v3a/reference/session-and-console-api/
---

# Session and Console API Reference

This page defines the supported core Session and Console API for SSHScript
v3.1 beta. Examples that teach a workflow belong in the tutorials and how-to
guides; this page focuses on signatures, results, errors, and lifetime rules.

## Package-level entry points

```python
sshscript.run_file(path, vars=None, showScript=False) -> int
sshscript.run_script(source, varGlobals=None, showScript=False) -> dict
sshscript.spy_imports()  # context manager
sshscript.get_logger()
sshscript.set_logger(userlogger=None, logname=None)
```

`spy_imports()` temporarily enables normal Python imports of `.spy` modules;
the importer is removed after the outermost context exits. `get_logger()`
returns the shared logger without adding a console handler. `set_logger()`
installs an application logger or explicitly configures SSHScript's console
logging. Importing SSHScript alone does not configure root logging.

## Object model

`Session` represents a local or SSH execution environment. A new `Session()`
is local. `connect()` returns a connected child Session. `shell()`, `su()`,
`sudo()`, and `enter()` return context managers whose `as` value is a console
object implemented by `SessionWrapper`.

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        with remote.shell() as console:
            console.exec_command("pwd")
finally:
    local.close(strict=True)
```

Do not instantiate `SessionWrapper` directly.

## Session construction and lifetime

```python
Session(parent=None)
```

A new Session is disconnected, has no command result, and does not change the
active SSHScript context. Entering `with session:` activates it on the current
thread. Leaving the last context of a remote Session closes that remote
Session; leaving a local Session context does **not** close the local Session.
Close locally created Sessions explicitly.

Parent Sessions own connected children and attempt to close them recursively.
A closed Session cannot create a new connection.

### Session properties

| Property | Meaning |
| --- | --- |
| `connected` | `True` when an SSH transport exists and is active. |
| `closed` | Whether `close()` has completed for the Session. |
| `host`, `username`, `port` | Connection identity; `None` for a new local Session. |
| `local_session` | The root local Session in a nested connection chain. |
| `sftp` | Lazily opened Paramiko SFTP client; requires an active SSH connection. |
| `stdout`, `stderr`, `exitcode` | Result of the latest command. |
| `logger` | SSHScript's configured logger. |
| `close_errors` | Tuple of `(operation, exception)` cleanup failures. |

`stdout`, `stderr`, and `exitcode` raise `ValueError` before the first command
result exists.

## One-shot commands

```python
session.exec_command(
    cmd: str,
    *,
    shell=None,
    shell_executable=None,
    **backend_options,
) -> tuple[stdout, stderr]

session(cmd, ...)  # alias
```

`cmd` must be one non-empty `str`. Lists, tuples, and other types raise
`TypeError`; an empty or whitespace-only string raises `ValueError`.

### Shell selection

| Value | Behavior |
| --- | --- |
| `shell=None` | Default. Detect whether the final string requires a shell. |
| `shell=False` | Local: split into an argument vector and launch without a shell. Remote: split, safely quote each argument, and send `exec ...` through the SSH server's command shell; shell operators are passed as arguments rather than interpreted as user shell syntax. |
| `shell=True` | Execute through a POSIX shell. |
| `shell="bash"` | Force shell execution using `bash`. |

A string-valued `shell` is shorthand for `shell=True` with that executable.
Supplying both a string-valued `shell` and `shell_executable` raises
`ValueError`.

Use `shlex.join(arguments)` with `shell=False` for dynamic argument lists:

```python
import shlex

command = shlex.join(["printf", "%s\\n", "hello world"])
stdout, stderr = session.exec_command(command, shell=False)
```

The local and remote implementations therefore preserve the same argument
boundaries, but remote `shell=False` is not a promise that no server-side
shell process participates.

### Results

The method returns `(stdout, stderr)` and stores the same objects on the
Session. `exitcode` stores the process status. A nonzero status does not raise
by default.

The two output objects are live, string-like buffers rather than immutable
Python strings. Use `str(stdout)` for a stable snapshot. Iteration can yield
received chunks and should not be assumed to produce exactly one complete
line per item.

### Backend options

Applicable keyword arguments are forwarded to the execution backend. Local
execution supports relevant `subprocess.run()` options such as `input`,
`timeout`, `env`, and `check`. Remote execution forwards relevant options to
Paramiko's `SSHClient.exec_command()`; SSHScript translates `env` to
Paramiko's `environment` option.

For a local one-shot command, `timeout=` is the `subprocess.run()` wall-clock
timeout. For a remote one-shot command, it is Paramiko's channel I/O timeout:
it is **not** a wall-clock command deadline and does not guarantee termination
of the remote process. Enforce an overall remote workflow deadline outside the
Session and reconcile the target's state after any ambiguous timeout.

These options are not perfectly symmetric. In particular, local `check=True`
can raise `subprocess.CalledProcessError`; do not treat it as a portable
local/remote contract. Local and remote string input also differ in newline
handling. Code that must work on both backends should inspect `exitcode` and
test its input protocol explicitly.

## SSH connections

```python
session.connect(
    host,
    username=None,
    password=None,
    port=22,
    policy=None,
    **connect_options,
) -> Session
```

Returns a connected child Session. `host` may be a hostname or the shorthand
`"user@host"`. Remaining supported options are passed to
`paramiko.SSHClient.connect()`.

```python
with local.connect(
    "example.net",
    username="ops",
    key_filename="/home/me/.ssh/id_ed25519",
    timeout=10,
    banner_timeout=10,
    auth_timeout=10,
) as remote:
    remote.exec_command("hostname", shell=False)
```

System host keys are loaded and unknown or changed keys are rejected by
default. Passing a permissive Paramiko policy must be an explicit, limited
bootstrap decision.

A connection created from an already connected Session tunnels through its
parent, enabling bastion workflows. `proxyCommand=...` is supported only from
a local parent; combining it with a nested connection raises
`NotImplementedError`. Direct proxy connections default their connection,
banner, and authentication timeouts to 30 seconds unless overridden.

`pkey_path=...` loads an RSA private key from the parent Session's host.
Supplying both `pkey_path` and `pkey` raises `ValueError`. The
`KEEPALIVE_INTERVAL` environment variable controls SSH keepalives; its default
is 60 seconds and `0` disables it.

Authentication, host-key, DNS, socket, timeout, and Paramiko failures
propagate to the caller.

## Keys and file transfer

```python
session.pkey(pathOfRsaPrivate, password=None) -> paramiko.RSAKey
```

Reads an RSA key locally for a local Session or through SFTP for a connected
Session. Missing files become `SSHScriptException`; parsing and decryption
errors propagate.

```python
session.upload(src, dst, makedirs=False, overwrite=True) -> tuple[str, str]
session.download(src, dst=None) -> tuple[str, str]
```

Both operations require an active SSH connection and return `(source,
destination)` after success. `upload()` returns the normalized absolute local
source and normalized remote destination. `download()` returns the remote
source as supplied and an absolute local destination. They raise filesystem,
SFTP, transport, or `SSHScriptException` errors on failure; they do not use
`exitcode`.

`upload()` accepts one existing local regular file. A remote destination that
ends in `/`, or is an existing directory, receives the source basename.
`makedirs=True` creates missing remote parents; `overwrite=False` requests
exclusive creation.

`download()` accepts one remote file. With `dst=None`, it writes to the local
current directory. An existing local directory receives the remote basename.

SFTP always uses the account that opened the SSH connection. Entering
`sudo()` or `su()` changes command identity, not SFTP identity.

## Persistent and interactive contexts

The following methods return context managers. Entering one yields a console.

```python
session.shell(command=None, *, get_pty=True)
```

Starts a persistent shell, `bash -i` by default. Commands share working
directory, environment, and other shell state.

```python
session.su(
    username,
    password=None,
    expect=None,
    initials=None,
    shell=True,
    login=True,
    get_pty=True,
)

session.sudo(
    password=None,
    username=None,
    expect=None,
    initials=None,
    shell=True,
    login=True,
    get_pty=True,
)
```

These open bounded identity-changing consoles. `initials` may be one command
or an iterable of setup commands. `PermissionError` is raised when expected
authentication prompts cannot be handled. The host's PAM and `sudoers`
policies remain authoritative.

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

Starts an interactive program. `expect` and `password` may handle an initial
authentication prompt; `prompt` identifies readiness for later input; `exit`
is sent while leaving the context. When `exit=None`, no exit text is sent.

## Execute source in a Session

```python
session.run(script, vars=None, showScript=False) -> dict
```

Runs Python or `.spy` source with this Session active and returns the resulting
namespace. The supplied namespace is copied. `showScript=True` prints the
translated source, returns an empty dictionary, and does not execute it.
Execution errors propagate.

At package level:

```python
sshscript.run_script(source, varGlobals=None, showScript=False) -> dict
sshscript.run_file(path, vars=None, showScript=False) -> int
```

Both create and close a fresh local Session. `run_file()` accepts exactly one
regular file path and returns zero on normal completion or the value passed to
`$.break(code)`. `$.exit(code)` and execution failures propagate.

## Session waiting and cleanup

```python
session.wait_for_silent(seconds, max_seconds=0) -> None
session.wait(seconds, max_seconds=0) -> None
session.wait_for_output(timeout=0, silent=False) -> bool
session.clear() -> None
```

These operate on the latest command channel. Silence is an observation, not
proof that a process completed. Zero means no overall timeout where
applicable. `clear()` clears the latest command's visible buffers and is a
no-op before the first command.

```python
session.close(strict=False) -> bool
```

Cleanup is recursive and best-effort. The method returns `True` only when all
steps succeed and records failures in `close_errors`. `strict=True` completes
the cleanup attempt and then raises `RuntimeError` if any step failed. Calls
are repeatable; `disconnect` is an alias.

## Console API

The object yielded by `shell()`, `su()`, `sudo()`, or `enter()` exposes:

| Property | Meaning |
| --- | --- |
| `stdout`, `stderr`, `exitcode` | Current console result and buffers. |
| `closed` | Whether the underlying channel is closed. |
| `local_session` | Root local Session. |
| `sftp` | Owning SSH connection's SFTP client. |
| `logger` | SSHScript logger. |

With a PTY, stderr may be merged into stdout.

### Console commands and input

```python
console.exec_command(command, **expectation_replies)
console(command, **expectation_replies)
console.send_line(command, **expectation_replies)
```

In a shell, `su`, or `sudo` context, these aliases execute one command and
return `(stdout, stderr)`. `command_timeout=60` sets the command deadline;
other keyword names are expected patterns whose values are replies. In an
`enter()` context, the same call is routed to interactive input.

```python
console.send(text) -> None
console.input(text, timeout=60) -> str | None
```

`send()` writes raw text without adding a newline. `input()` sends a line. In
an interactive context, `input()` returns `"prompt"`, `"exited"`, or
`"silent"`; outside one it normally returns `None`. Invalid input, timeout,
EOF, broken pipe, and transport errors propagate.

### Pattern matching

```python
console.expect(
    pattern,
    timeout=None,
    stdout=True,
    stderr=True,
    silent=False,
)
```

`pattern` may be a regex string, compiled regex, callable, list or tuple of
alternatives, or a dictionary mapping patterns to reply strings. String
patterns are case-insensitive. A successful call returns the regex match,
successful callable, or completed dialog mapping. A timeout raises
`TimeoutError`, unless `silent=True`, in which case it returns `None`.
Disabling both output streams raises `ValueError`.

Matching advances internal cursors but does not erase visible output.

### Waiting, signaling, and buffers

```python
console.wait_for_silent(seconds, max_seconds=0) -> None
console.wait(seconds, max_seconds=0) -> None
console.wait_for_output(timeout=0, silent=False) -> bool
console.send_signal(signal_value) -> None
console.clear() -> None
console.set_prompt(prompt) -> None
console.log(level, message, *args, **kwargs) -> None
```

`send_signal()` expects a `signal.Signals` value. `clear()` resets the active
buffers. `wait_for_output()` returns `False` on timeout only when
`silent=True`; otherwise timeouts raise. `log()` forwards a standard numeric
logging level, message, format arguments, and logging keywords through the
shared SSHScript logger with channel context.

The console can create nested `shell()`, `su()`, `sudo()`, and `enter()`
contexts. Its `upload()`, `download()`, and `pkey()` methods delegate to the
owning Session.

## Exception model

SSHScript distinguishes three outcomes:

1. A command ran and returned a status. Inspect `exitcode`; nonzero does not
   normally raise.
2. The API, operating system, interactive protocol, filesystem, network, SSH,
   or transfer operation failed. An exception propagates.
3. Cleanup failed. `close()` returns `False` and fills `close_errors`, or
   `close(strict=True)` raises after cleanup.

`SSHScriptException(message, errno=1)` is the package-specific base and
provides `message` and `errno`. Public methods also intentionally raise
standard Python, subprocess, filesystem, socket, and Paramiko exceptions.

## Compatibility and implementation surfaces

The following names exist but should not be the foundation of new Module API
code:

- `open()` aliases `connect()`;
- `send_line()` aliases Session `exec_command()`;
- Session `onedollar()` emits `DeprecationWarning` and delegates to
  `exec_command()`;
- Session `twodollars()` emits `DeprecationWarning` and forces shell
  execution; and
- console `send_line` is an alias for command execution.

Do not rely on dollar-named aliases exposed by console wrappers; their
compatibility behavior is not the Session contract above.

`Session.exit(code=0, message="")` is `.spy` runner control flow: it raises a
control-flow exception for the script runner and is not a general application
shutdown method. `Session.session` is a self-reference and `Session.dollar`
exposes the latest internal execution object; neither is needed for ordinary
Module API code.

Console `session`, `os_name`, and `environ()` are currently compatibility or
implementation surfaces rather than portable v3.1 contracts. In particular,
`console.session` does not currently expose the owning Session, and environment
updates depend on the active channel backend. They are intentionally not
documented as supported application interfaces until their contracts and tests
are stabilized.

Use `exec_command()`, `connect()`, and an explicit `shell=` choice in new
code.

## Runtime validation

Commands must be nonempty strings; wrong types raise `TypeError`, and empty
commands raise `ValueError`. Persistent commands must contain only one line.
`get_pty` accepts only `None` or bool. The internal `for_with` selector accepts
only bool. Text matching rejects compiled bytes regular expressions with
`TypeError`; appended output must be str.

Invalid console/channel lifecycle transitions raise `RuntimeError`. Failed
listener removal, duplicate hijack/release, and last-layer removal preserve
state. Closed channel operations raise `BrokenPipeError`; a channel ending
while a caller waits raises `EOFError`; timeout raises `TimeoutError`.
Disconnected `Session.sftp`, upload, and download raise `SSHScriptException`.
Paramiko failures retain their original exception and traceback. See
[Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

Last Updated: 2026-09-21 17:45:03
