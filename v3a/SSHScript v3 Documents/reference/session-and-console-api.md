---
title: "Session and Console API Reference"
parent: "Reference"
grand_parent: "SSHScript Documentation"
nav_order: 1
permalink: /v3a/reference/session-and-console-api/
---

# Session and Console API Reference

> **Version scope:** The base command API is available in 3.1.5.
> Session settings, managed deadlines, and jobs below are features available in 4.0.2.

This page defines the supported core Session and Console API for the SSHScript
v3.1 line, including the explicitly marked 4.0 managed-command API. Examples that teach a
workflow belong in the tutorials and how-to guides; this page focuses on
signatures, results, errors, and lifetime rules.

<a id="session-settings-unreleased-source-api"></a>

## Session settings (4.0 source API)

`session.set(check=..., verbose=..., verbose_stderr=..., log_level=...,
policy=...)` validates all supplied settings before applying changes.
`session.get()` returns a copy of the settings dictionary; `session.get(name)`
reads one setting. Matching properties use the same storage. Unknown setting
names raise `ValueError`; invalid policy values raise `TypeError`.

| Setting | Accepted values | Default |
| --- | --- | --- |
| `check` | bool | `False` |
| `verbose` | bool | application/environment default |
| `verbose_stderr` | bool | application/environment default |
| `log_level` | logging integer or level name | application logger level |
| `policy` | Paramiko `MissingHostKeyPolicy` instance, subclass, or `None` | `None` (RejectPolicy) |

```python
import paramiko
from sshscript import Session

session = Session()
try:
    session.set(policy=paramiko.AutoAddPolicy())
    assert session.get("policy") is session.policy
    session.policy = None
finally:
    session.close()
```

Child Sessions copy the parent's settings at creation. A policy object itself
is shared, so custom policies with mutable state must account for reuse.
Changes affect future connections only. These settings are not in published
3.1.5; see the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/).

<a id="managed-commands-unreleased-source-api"></a>

## Managed commands (4.0 source API)

`Session.start(cmd, *, shell=None, shell_executable=None, timeout=None,
stop_timeout=3, capture_limit=1048576, check=False, input=None, env=None,
get_pty=False)` returns a `CommandJob` with `wait()`, `stop()`, `iter_stdout()`,
`done`, and a context manager. Timeout is a total local/SSH command budget;
None means no execution deadline. Local get_pty=True is unsupported.

`exec_command(..., command_timeout=...)` opts into the same managed execution;
legacy timeout remains unchanged and cannot be combined with command_timeout.
Managed calls return `JobResult`, a CommandResult subclass with stop_reason,
termination_status and stdout/stderr truncation flags. Missing status is None.
Deadline expiry raises `CommandTimeoutError` with a partial result and text
output, even when check=False. start() does not alter Session.last_result.

These APIs are not in published 3.1.5. The legacy result/buffer rules below
apply when command_timeout is omitted. See the
[timeout and cancellation guide]({{ site.baseurl }}/v3a/security-and-operations/timeouts-retries-and-cleanup/)
for bounded output, cleanup guarantees, and a remote tcpdump/Ctrl-C example.

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
| `stdout`, `stderr`, `exitcode` | Latest command buffers and status. |
| `last_result` | Latest completed one-shot CommandResult, or None before completion. |
| `logger` | SSHScript's configured logger. |
| `close_errors` | Tuple of `(operation, exception)` cleanup failures. |

`stdout`, `stderr`, and `exitcode` raise `ValueError` before the first command
result exists.

## One-shot commands

```python
session.exec_command(
    cmd: str | list[str] | tuple[str, ...],
    *,
    shell=None,
    shell_executable=None,
    check=False,
    **backend_options,
) -> CommandResult  # unpack stdout, stderr, exitcode

session(cmd, ...)  # alias
```

`cmd` is one nonempty string or a nonempty list/tuple of string arguments, not
a batch of commands. Argv permits empty data arguments but not an empty
executable or NUL. Sequences require `shell=None`/`False` with no
`shell_executable`; wrong types raise `TypeError`, invalid values or
combinations raise `ValueError`. `check` must be bool.

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

Pass dynamic argument lists directly, or retain `shlex.join()` with `shell=False`:

```python
result = session.exec_command(["printf", "%s\\n", "hello world"], check=True)
stdout, stderr, exitcode = result
```

The local and remote implementations therefore preserve the same argument
boundaries, but remote `shell=False` is not a promise that no server-side
shell process participates.

### Results

`CommandResult` supports three-value unpacking/indexing: stdout, stderr, exitcode.
Output is an immutable text snapshot. It also stores `host`, `duration`, and
`command`; see [Results and Error Model](../../concepts/results-and-error-model/)
for their exact definitions. The Session retains the result as `last_result`,
as well as its existing latest-output buffer properties.

`check=True` is handled by SSHScript on both backends. Nonzero status raises
`subprocess.CalledProcessError` after result capture; the exception's `result`
contains the snapshot. Its `stdout`/`stderr` are text and its `cmd` is the
normalized string or argv tuple. `check=False` returns nonzero status as data.

### Backend options

Applicable keyword arguments are forwarded to the execution backend. Local
execution supports relevant `subprocess.run()` options such as `input`,
`timeout` and `env`. SSHScript consumes `check` before backend dispatch. Remote execution forwards relevant options to
Paramiko's `SSHClient.exec_command()`; SSHScript translates `env` to
Paramiko's `environment` option.

For a local one-shot command, `timeout=` is the `subprocess.run()` wall-clock
timeout. For a remote one-shot command, it is Paramiko's channel I/O timeout:
it is **not** a wall-clock command deadline and does not guarantee termination
of the remote process. Enforce an overall remote workflow deadline outside the
Session and reconcile the target's state after any ambiguous timeout.

The `check` policy is symmetric; backend timeout and input behavior are not.
Local and remote string input differ in newline handling. Test protocol-sensitive
input on each backend.

## Compile-only script validation

`sshscript.check_file(path)` compiles one Python/`.spy` file and returns 0.
It does not create a Session, execute user code, import user modules, or connect.
Syntax errors retain the original file/line/source; filesystem errors propagate.
This does not validate shell syntax, import availability, or remote behavior.
Use `sshscript --check file.spy` for the equivalent CLI check.

## SSH connections

```python
session.connect(
    host,
    username=None,
    password=None,
    port=None,
    policy=...,  # 4.0: omitted argument uses the Session setting.
    *,
    ssh_config=None,
    **connect_options,
) -> Session
```

In published 3.1.5, the signature uses `policy=None`. In SSHScript 4.0,
an omitted policy uses `session.policy`; explicit `None` selects default
RejectPolicy. A supplied policy overrides only this connection, without
changing inherited child settings. The omitted value is an internal sentinel.

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

Local connections read `~/.ssh/config` by default. Set `ssh_config=False` to
opt out, or supply a path. Explicit arguments override config; `port=None`
means unspecified and falls back to 22. Nested connections skip local config
unless a file is explicitly selected. `Session.resolve_connection(...)`
previews effective settings without connecting. It accepts `host`, `username`,
`port`, `ssh_config`, and connection options, and returns a dict of effective
Paramiko arguments plus `proxyCommand` when needed.

Supported config keys and ProxyJump prerequisites are documented in
[Connections, Authentication, and Bastions]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/Basic/connect/).

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

<a id="unreleased-completed-console-command-results"></a>

## 4.0: completed console command results

`shell(command)`, `shell.exec_command(command)`, and their su/sudo equivalents
return immutable `CommandResult` snapshots with three-value unpacking. Commands
remain strings. Save the result; `check=True` failures carry `.result`.
`console.stdout`/`stderr` remain live buffers, and `console.exitcode` is latest
status. This changes published 3.1.5 two-value console unpacking. Inside enter(),
console calls send input and retain readiness-status returns instead.
For continuous programs choose a managed job or an enter()/expect() scope with
an explicit stop condition; see the
[canonical guide]({{ site.baseurl }}/v3a/recommended-api/#unreleased-command-results-and-long-running-programs).

<a id="unreleased-console-foreground-jobs"></a>

## 4.0: console foreground jobs

```python
console.start(command, *, timeout=60, stop_timeout=3,
              capture_limit=1024 * 1024, check=...) -> CommandJob
```

Available in Bash shell/sudo/su contexts, including `$.start()` in `.spy`.
Accepts one command string and preserves console cwd/environment/identity.
check inherits Session policy. timeout is a total budget; None explicitly disables
it. Only one foreground job may occupy a channel; other console operations and
cross-thread operations are rejected. Use job.iter_stdout(), wait() and stop().
No start() inside enter(). Completed synchronous console calls remain unchanged.

Completion and PTY Ctrl-C recovery verify the original UID and shell PID. Pipe
cancellation cannot safely interrupt and disables the console. Unconfirmed
recovery raises with partial `.result`; a deadline raises CommandTimeoutError.
PTY streams may merge and output capture is bounded. Change identity with nested
su/sudo before starting; detached jobs and raw privilege shells are unsupported.
See the [full contract and runnable examples]({{ site.baseurl }}/v3a/recommended-api/#unreleased-foreground-jobs-inside-shell-sudo-and-su).

## Persistent and interactive contexts

The following methods return context managers. Entering one yields a console.

```python
session.shell(command=None, *, get_pty=True)
```

Starts a persistent shell, `bash -i` by default. Commands share working
directory, environment, and other shell state. The whole block scopes the
shell's lifetime; it does not return an aggregate CommandResult or check every
command's status. Successful scope exit or a final zero exit status does not
prove all commands succeeded. Check required commands individually.

```python
session.su(
    username,
    password=None,
    expect=None,
    initials=None,
    shell=True,
    login=True,
    get_pty=True,
    enter_timeout=10,  # 4.0 source API.
)

session.sudo(
    password=None,
    username=None,
    expect=None,
    initials=None,
    shell=True,
    login=True,
    get_pty=True,
    enter_timeout=10,  # 4.0 source API.
)
```

These open identity-changing consoles. `initials` may be one command or an
iterable of setup commands. The host's PAM and `sudoers` policies remain
authoritative. `enter_timeout` and the authenticated entry contract below are
**features available in 4.0.2**, unavailable in the published 3.1.5 package.

<a id="authenticated-susudo-entry-unreleased"></a>

### Authenticated su/sudo entry (4.0)

`Session.su()`, `Session.sudo()`, and their nested console equivalents accept
`enter_timeout=10` (positive finite seconds). The deadline covers entry's lock
acquisition, password conversation, target-shell readiness, and `initials`.
It begins in `__enter__`; creating a base shell or probing `console_info` in the
factory is outside that deadline. Success returns immediately, without a fixed
password-verification delay. On context exit, the same duration bounds waiting
for the target shell to return to its parent.

The requested command emits a fresh authentication marker only after su/sudo
has started it as the target account. It checks effective UID against `id -u
USERNAME`; a second handshake checks that UID and shell PID survived shell
startup. PTY contexts also wait for their own unique prompt. Output silence,
a missing error message, and a missing password prompt are never success
criteria. Passwordless entry is supported, including when a password was
provided but never requested. The supplied password is sent at most once.
Each authenticated console context is single-use; create a new context for an
explicit retry.
Default prompt matching covers standard English password prompts; `expect=`
remains available for other authentication prompt formats.

#### Interactive usage

These transcripts require a real local account and its authentication policy;
they are manual examples, separate from credential-free CI coverage.
Read passwords with `getpass` rather than storing them in the script. The new
behavior requires 4.0.2 and does not apply to the installed 3.1.5 release.

Open a root console through sudo and allow up to 15 seconds for entry:

```pycon
>>> from contextlib import closing
>>> from getpass import getpass
>>> from sshscript import Session
>>> with closing(Session()) as local:
...     with local.sudo(password=getpass("sudo password: "), enter_timeout=15) as root:
...         stdout, stderr, exitcode = root("id -u")
...         print(str(stdout).strip())
0
```

Enter an existing account named `alice` from a persistent shell. Replace the
account name with your intended target; su normally asks for the target
account's password, whereas sudo's password choice is determined by sudo policy.

```pycon
>>> with closing(Session()) as local:
...     with local.shell() as shell:
...         with shell.su("alice", password=getpass("su password: "), enter_timeout=15) as user:
...             stdout, stderr, exitcode = user("id -u")
...             print(str(stdout).strip())
```

For a configured passwordless sudo policy, use `local.sudo(password=None,
enter_timeout=15)`. If a password is actually requested, entry raises
`PermissionError` before the block body runs. Both factories also accept
`shell=False` to start su/sudo directly, `get_pty=False` to use pipes, and
`login=False` to omit login mode. Host policy and the installed utility may
reject these combinations. Nested console `shell`/`get_pty` arguments remain
compatibility placeholders; they do not reconfigure an existing channel.

#### Failure handling

Explicit authentication rejection or a second password request raises
`PermissionError`; an early command exit or identity mismatch raises
`RuntimeError`. An unresolved deadline raises `TimeoutError`. I/O failures
propagate. A failure has a separate **two-second recovery budget**: observe
return to the parent, or interrupt unresolved PTY authentication, then verify
the parent's original UID/PID. If this cannot be confirmed, the channel is
marked failed and rejects further commands. A direct `shell=False` console
has no parent to recover; its owning context closes the channel on entry
failure. Channel resource cleanup can take additional time. There is no
password retry or automatic fallback to the original account.

Handle entry failure outside the `with` statement; its body has not run unless
the readiness handshake completed. A `TimeoutError` means that completion was
not confirmed, rather than proof of a bad password. `enter_timeout=True`, zero,
negative values, NaN, and infinity are not accepted.

After a failed nested entry, use the parent only if recovery was confirmed.
`console.closed` alone cannot establish this: an open channel may have been
marked failed and will reject subsequent commands. There is no public recovery
status flag; attempting another parent command propagates the stored channel
failure if recovery was unconfirmed. Do not attempt to clear that failure.
Create a new console context for an intentional retry, and a new underlying
channel when the old channel is unusable. Context unwinding preserves the
original exception and releases the console's lock and thread-stack entry.

#### Platform behavior and custom commands

Bash remains required and is found through the target's PATH, including
FreeBSD's usual `/usr/local/bin` installation. su uses the cached
`session.console_info['is_su_pty_ok']` capability to select `--pty`; the handshake
does not depend on a distribution name or a fixed PAM delay. su's `-c` follows
USERNAME so that BSD passes it to the target shell instead of interpreting it
as a login class. The existing sudo-to-su route for a non-root target and login
mode are retained. If Bash, `id`, or the necessary shell behavior is unavailable,
entry fails rather than being treated as successful.

`console_info` is a cache for tool capability probes. In the current source it
contains `is_su_pty_ok`; it does not expose a populated OS/distribution inventory.
Prefer a tool capability result over a distribution-name guess. The bootstrap
also prevents the outer login shell from expanding its dollar expressions when
sudo reconstructs argv for `-i`; available Bourne and csh-family shells are
covered by the protocol tests.

Custom nested `command=` strings now require a bootstrap placeholder. Use
`{auth_command}` where the generated Bash command is ordinary command argv,
for example `command="sudo -k -S {auth_command}"`. Use
`{auth_command_quoted}` where the command must be one shell argument, for
example `command="su - alice -c {auth_command_quoted}"` together with
`username="alice"`. Do not add your own quotes around either placeholder.
Templates without a placeholder are rejected before sending them. This is a
compatibility change: an arbitrary interactive command cannot guarantee an
authenticated startup marker. `Session.enter()` remains the lower-level API
for application-specific conversations and does not provide this su/sudo
handshake guarantee.

Credential-free coverage is in `unittest/test_console_authentication.py`.
It uses real PTY/pipe channels and simulated authentication, plus available
Bourne/csh-family shells. These checks do not establish real authentication
compatibility with every OS, sudo policy, PAM stack, or utility version;
real Linux (util-linux and BusyBox), FreeBSD, and macOS verification is needed
before release. See the source checkout's `unittest/README.console-authentication.md`
for commands, coverage, and the native-system validation matrix.

### General interactive programs

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

One-shot `Session.exec_command(input=data)` / `Session.start(input=data)` use
exact stdin in 4.0 source, with UTF-8 strings, unchanged bytes, no added
newline, and EOF after supplied input (including empty data). `input=None` keeps
the existing backend policy; legacy local execution may inherit stdin.
Published 3.1.5 legacy SSH string input adds a
newline; migrate to explicit `input=answer + "\n"` where a consumer needs a line.
Terminal password prompts may require `enter()` and a PTY instead of stdin.


```python
console.exec_command(command, **expectation_replies)
console(command, **expectation_replies)
console.send_line(command, **expectation_replies)
```

In 4.0 source, shell/su/sudo aliases execute a command and return an
immutable CommandResult. Unpack `stdout, stderr, exitcode`, or save the result
and read named fields. Published 3.1.5 console calls retain their two-buffer
returns. `command_timeout=60` bounds this command's console wait; other keyword
names are expected patterns mapped to replies. Shell calls inherit Session
`check`, with a per-command bool override; failures carry `.result`.
Inside enter(), calls are routed to interactive input and retain readiness-status
returns. Live `console.stdout`/`stderr` remain available for expect/send workflows.
The console deadline is not the managed Session job contract, and timeout alone
does not prove process termination. For continuous programs see the
[command choices]({{ site.baseurl }}/v3a/recommended-api/#unreleased-command-results-and-long-running-programs).


```python
console.send(text) -> None
console.input(text, timeout=60) -> str | None
```

`send()` writes exact text without adding a newline and only confirms the write.
`input()` appends exactly one `"\n"`, retaining any existing newline, then waits:
`input("answer\n")` sends `"answer\n\n"`; `input("")` presses Enter. Prefer these
explicit APIs for replies inside `enter()`; context-dependent calls and
`send_line()` remain compatibility forms. In
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

One-shot commands accept nonempty strings or nonempty lists/tuples of string
arguments. Wrong types raise `TypeError`; empty commands or invalid shell/argv
combinations raise `ValueError`. Persistent commands must contain only one line.
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

Last Updated: 2026-10-09 10:40:03
