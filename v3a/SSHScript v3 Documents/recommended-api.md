---
title: "Recommended SSHScript API"
parent: "SSHScript Documentation"
nav_order: 0
permalink: /v3a/recommended-api/
---

<!-- Generated from API_GUIDE.md; do not edit this copy. -->

# Recommended SSHScript API

This is the canonical entry point for new code and AI-generated examples.
**Current contract: 4.0.2**, Python 3.11+. Sections marked **4.0** require
SSHScript 4.0.2; installing `sshscript==3.1.5` does not provide them.
Examples labelled 3.1.5 remain verified compatibility examples for that baseline.
Pin the exact artifact version and record it with execution diagnostics when
handing off automation. See [version policy and migration]({{ site.baseurl }}/v3a/migration-and-releases/version-policy/).

SSHScript aims to help engineers and AI agents execute, understand, and hand
off automation reliably. Keep the execution host and retained result with the
script's version and inputs; distinguish completion, failure, timeout, and
unknown termination. Verify application outcomes separately: a zero command
exit status does not prove that a deployment succeeded, and closing an SSH
channel does not prove that its remote process stopped. Structured execution
identifiers and handoff reports are future work, not a current API guarantee.

## Recommended choices

| Need | Use |
| --- | --- |
| A command with dynamic arguments | `session.exec_command([program, arg, ...], check=True)` |
| Pipelines or shell expansion | A string with explicit `shell=True` or `shell="bash"`; quote dynamic values |
| Retain output | Save the returned result; read `result.stdout`, `stderr`, `exitcode` |
| Shared shell directory/environment | `session.shell()`; check each required command; **4.0:** save its CommandResult |
| SSH | `with local.connect(...) as remote:`; retain host-key verification |
| Compact script | One `$` in a `.spy` file; use `$(argv, check=True)` for dynamic arguments |
| Consistent total deadline | **4.0:** `exec_command(command_timeout=...)` |
| Long-running program | **4.0:** `start(timeout=None)`, `stop()`, `wait()` |
| Session-wide failure/output policy | **4.0:** `set(...)`, `get(...)`, or matching properties |

## One command, one retained result (4.0; compatible with 3.1.5)

Install the current release with `python -m pip install "sshscript==4.0.2"`.
For reproducing only the historical compatibility baseline, explicitly install
`sshscript==3.1.5`; the 4.0 sections require the current release.
An argv list is one command, not a batch. Shell-looking argument text stays data.

<!-- example: {"id":"argv", "profile":"3.1.5", "stdout":"a; b\n"} -->
```python
from contextlib import closing
import sys
from sshscript import Session

with closing(Session()) as local:
    result = local.exec_command(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "a; b"],
        check=True,
    )
    local.exec_command([sys.executable, "-c", "pass"], check=True)
    print(result.stdout.strip())  # Still the first command's output.
```

`CommandResult` is immutable; unpacking yields exactly stdout, stderr, exitcode.
`check=True` raises `subprocess.CalledProcessError` on nonzero exit, with text
stdout/stderr and `.result`. A timeout or transport error is not an exit status.

<!-- example: {"id":"failure", "profile":"3.1.5", "stdout":"failed: 7\n"} -->
```python
from contextlib import closing
import subprocess
import sys
from sshscript import Session

with closing(Session()) as local:
    try:
        local.exec_command([sys.executable, "-c", "raise SystemExit(7)"], check=True)
    except subprocess.CalledProcessError as error:
        print(f"failed: {error.returncode}")
```

## SSH and optional dollar syntax (4.0; compatible with 3.1.5)

Replace the example host with your configured host and verified known-host key.
CI executes this block with a local SSH protocol fixture in place of the login;
it does not contact example.net. OpenSSH integration tests cover the transport
separately in CI.

<!-- example: {"id":"ssh", "profile":"3.1.5", "fixture":"ssh", "stdout":"ready\n"} -->
```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    with local.connect("ops@example.net", timeout=10,
                       banner_timeout=10, auth_timeout=10) as remote:
        result = remote.exec_command(["printf", "%s", "ready"], check=True)
        print(result.stdout)
```

### Private-key paths and nested connections

`parent.connect(..., pkey_path=path)` loads an RSA private key from the
**calling parent Session's host**. A local Session reads the file on localhost;
a Session connected to host1 reads it on host1 through SFTP before connecting
to host2. `connect()` returns a child Session and leaves the parent on its
original host. Calling the original local Session again therefore still reads
the key on localhost.

For example, `local.connect("host1", pkey_path="/local/key_rsa")` reads
`/local/key_rsa` locally and returns `host1`. Then
`host1.connect("host2", pkey_path="/remote/key_rsa")` reads `/remote/key_rsa`
on host1. In `.spy`, an inner `with $.connect(...)` uses the outer scope's
current Session as its parent.

`key_filename=` is forwarded to Paramiko and reads from the local Python
process's filesystem even for nested connections; it supports additional key
formats. For an encrypted RSA key, use
`pkey=parent.pkey(path, password=key_passphrase)` to retain the same host-based
reading rule. Supplying both `pkey_path` and `pkey` raises `ValueError`.
See the [agent guide's complete nested example](https://iapyeh.github.io/sshscript/v3a/ai-agents/guide/#ssh-connections-and-private-key-paths).

### Host-key sources (unreleased)

This section describes the development checkout, not published SSHScript 4.0.2.
`known_hosts` selects the host-key trust source independently of `policy`:

| Value | Sources, in order |
| --- | --- |
| `"parent"` (new default) | Only the calling Session's host |
| `"local"` | Only the root localhost Session |
| `"chain"` | Calling Session, then each ancestor through localhost |

For localhost → host1 → host2 → host3, `host2.connect("host3",
known_hosts="chain")` consults host2, host1, then localhost. The nearest source
with a record for the resolved target hostname and port is authoritative.
A matching key is accepted; a changed key is rejected even if a more distant
source matches. Only absence of a target record permits continuing the chain.
Different key algorithms do not permit falling back to another source.

Each source reads its own `known_hosts_path`, or `~/.ssh/known_hosts` if unset.
Remote files are read over SFTP as that Session's original SSH login account;
SSH handshakes, user authentication and host-key verification still run in the
local Python process. Neither sudo/su nor a nested connection changes the SFTP
account. Remote `~/` paths refer to the login account's SFTP home; `~user` paths
are unsupported. Relative remote paths use the SFTP working directory.

```py
local.set(known_hosts="chain")
# After connecting to host1 and host2:
host1.set(known_hosts_path="/home/ops/.ssh/known_hosts")
host2.set(known_hosts_path="/etc/ssh/ssh_known_hosts")
with host2.connect("deploy@host3", pkey_path="/home/ops/.ssh/host3_rsa") as host3:
    result = host3.exec_command(["hostname"], check=True, command_timeout=10)
```

The strategy is inherited by future child Sessions; the path is host-specific
and is **not inherited**. `known_hosts_path=None` restores the standard path.
A `connect(known_hosts=...)` override affects only that connection; it does not
change the parent setting or the child's inherited strategy. `set()`, `get()`
and matching properties expose both settings. `known_hosts_path` accepts text
paths and `PathLike[str]`; it is a Session setting, not a `connect()` keyword.

`pkey_path` always reads only from the calling Session's host, including with
`known_hosts="chain"`; private keys are never searched through ancestors.

An absent trust file, permission failure, read failure, invalid UTF-8 or invalid
entry raises an error; no distant source or permissive policy bypasses it.
Empty files, comments, plain host-key entries (including comma-separated names)
and hashed hostnames are supported. OpenSSH markers such as `@cert-authority`
and `@revoked`, wildcard/negated host patterns and unsupported key types raise
an error rather than being silently ignored. A source file is fully parsed
before its records are used. Nonstandard ports use `[hostname]:port` records.

When every selected source lacks the target, `policy` handles the unknown key.
`AutoAddPolicy` accepts it into the new client's memory only; these trust files
are read-only and are not automatically updated locally or remotely.

**Migration:** published 4.0.2 always loads localhost host keys. The new default
`"parent"` makes nested host-key sources consistent with `pkey_path`. To retain
the previous behavior, set `local.set(known_hosts="local")` before connecting.
All strategies require a readable, valid file, including the default localhost
path. Unlike published 4.0.2, a missing local file is an error; create an empty
file if the configured missing-key policy should handle unknown hosts.

### Private keys readable only in a privileged console

Remote `pkey()` and `pkey_path` use SFTP with the original SSH login account.
Entering `sudo()` or `su()` does not change that identity, so even
`$.pkey("/root/.ssh/id_rsa")` inside a root console can fail with a permission
error. When authorized, read the file with a console command and construct
the Paramiko key from its captured text:

This manual example requires a real privileged console and SSH endpoints;
it is excluded from credential-free executable examples.

```py
from contextlib import closing
from io import StringIO
import paramiko
from sshscript import Session

with closing(Session()) as local:
    with local.connect("ops@host1.example.net", timeout=10,
                       banner_timeout=10, auth_timeout=10) as host1:
        with host1.sudo() as root:
            key_result = root("cat /root/.ssh/id_rsa", check=True, command_timeout=10)
            key = paramiko.RSAKey.from_private_key(StringIO(key_result.stdout))
        with host1.connect("deploy@host2.example.net", pkey=key, timeout=10,
                           banner_timeout=10, auth_timeout=10) as host2:
            result = host2.exec_command(["hostname"], check=True, command_timeout=10)
            print(result.stdout)
```

The example requires authorized sudo/SSH access and verified host keys.
Configure output logging/display to keep private-key text out of logs before
running the read; do not print or report `key_result` or its stdout. Key text
also remains in console buffers. Use the matching Paramiko key class for
other formats; encrypted RSA keys need `password=` on `from_private_key()`.
An authorized `su()` console can supply the text in the same way.

The console returned by `shell()`/`sudo()`/`su()`/`enter()` has no `connect()`
method, so `$.connect()` is unavailable while a console is current in `.spy`.
A retained Python Session can still call `connect()` during an active console;
the connection uses its original SSH transport and does not inherit console
privilege. The example leaves the console first and calls the retained
`host1.connect(pkey=key)`, which needs no SFTP key read. See the
[agent guide's `.spy` equivalent](https://iapyeh.github.io/sshscript/v3a/ai-agents/guide/#keys-readable-only-after-sudosu).

### Optional dollar syntax

Save dollar syntax as `.spy`, run with `sshscript file.spy`, and syntax-check
without execution using `sshscript --check file.spy`.

<!-- example: {"id":"dollar", "profile":"3.1.5", "stdout":"ready\n"} -->
```python
result = $(["printf", "%s", "ready"], check=True)
print(result.stdout)
```

<a id="unreleased-settings-and-managed-jobs"></a>

## 4.0: settings and managed jobs

Use SSHScript 4.0.2 for the following examples. CLI `-v`, `--stderr`, and
`--debug` override root defaults only for that execution. Child Sessions copy
their parent's settings. `set()` validates before changing anything; `get()`
returns a copy. Explicit command options override Session policy.

The `policy` setting controls future SSH connections. It defaults to `None`
(Paramiko's RejectPolicy) and accepts a Paramiko `MissingHostKeyPolicy` instance
or subclass. For example, `local.set(policy=paramiko.AutoAddPolicy())` makes
subsequent `local.connect(...)` calls accept unknown host keys. Import `paramiko`
before using its policies. The matching `local.policy` property and
`local.get("policy")` use the same setting.

An explicit `connect(policy=...)` overrides the setting for that connection;
`connect(policy=None)` restores default rejection for that connection. These
overrides do not change the settings inherited by child Sessions. Children copy
the settings dictionary at creation; the policy object itself is shared, so
custom policies with mutable state must account for reuse. Changing the setting
does not reconfigure existing connections.

<!-- example: {"id":"settings", "profile":"4.0.2", "stdout":"True\n1\n"} -->
```python
from contextlib import closing
import paramiko
from sshscript import Session

with closing(Session()) as local:
    local.set(check=True, verbose=False, log_level="WARNING",
              policy=paramiko.AutoAddPolicy())
    print(local.get("check"))
    result = local.exec_command(["false"], check=False, command_timeout=5)
    print(result.exitcode)
```

`command_timeout` is a total command budget on both backends; output does not
reset it. `CommandTimeoutError` includes partial output and termination status.
The legacy `exec_command(timeout=...)` retains different subprocess/Paramiko
semantics; do not combine it with `command_timeout`.

For an indefinite command such as tcpdump, use `start(timeout=None)`. This safe
local example uses a small Python process instead of capturing network traffic:

<!-- example: {"id":"stop", "profile":"4.0.2", "stdout":"cancelled confirmed\n"} -->
```python
from contextlib import closing
import sys
from sshscript import Session

with closing(Session()) as local:
    with local.start(
        [sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"],
        timeout=None, stop_timeout=1,
    ) as job:
        try:
            next(job.iter_stdout())
        finally:
            result = job.stop()  # Also use this after catching KeyboardInterrupt.
        print(result.stop_reason, result.termination_status)
```

Local stop sends SIGINT, then escalates if needed. Remote PTY stop attempts
Ctrl-C; non-PTY stop closes the channel. Closure alone never confirms remote
termination. Inspect `termination_status`; `unknown` requires reconciliation.
Managed output retains bounded tails (default 1 MiB per stream), with truncation
flags. `iter_stdout()` yields text chunks and reports queue overflow explicitly.

<a id="unreleased-exact-stdin-and-explicit-interactive-replies"></a>

## 4.0: exact stdin and explicit interactive replies

`exec_command(input=data)` and `start(input=data)` send stdin unchanged on local
and SSH backends. Strings are encoded as UTF-8; bytes retain their exact values.
No newline is added, existing newlines are preserved, and stdin is closed after
sending supplied data (including an empty string or bytes). `input=None` supplies
no payload: legacy local execution can inherit stdin, whereas SSH and managed
execution close their stdin write side. This preserves the existing no-input
policy; use empty input to explicitly supply no data and EOF. This fixes the
legacy SSH behavior which appended a newline to strings: if a consumer
needs a line, migrate `input=password` to `input=password + "\n"` explicitly.
Published 3.1.5 still has the legacy SSH behavior.

<!-- example: {"id":"exact-stdin", "profile":"4.0.2", "stdout":"'abc'\n'abc\\n'\n"} -->
```python
from contextlib import closing
import sys
from sshscript import Session

with closing(Session()) as local:
    command = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"]
    print(repr(local.exec_command(command, input="abc", check=True).stdout))
    print(repr(local.exec_command(command, input="abc\n", command_timeout=5,
                                  check=True).stdout))
```

A shell command and a reply use the same channel but have different completion
boundaries. SSHScript follows the explicit context; it does not guess from the
text or its newline characters.

| Intent | API | Newline and completion behavior |
| --- | --- | --- |
| Execute a command | `shell(command)` / `shell.exec_command(command)` | Submits the command and waits for CommandResult / exit status |
| Answer a program | `program.input(answer)` inside `enter()` | Appends exactly one `"\n"`, then waits for readiness, exit, or silence |
| Write exact text or control characters | `program.send(data)` | Adds nothing; returning only confirms the write |
| Supply one-shot stdin | `session.exec_command(..., input=data)` | Adds nothing; the command result follows command completion |

`input("answer\n")` sends `"answer\n\n"`; it never removes a newline supplied by
the caller. `input("")` presses Enter. `send("answer\n")` writes exactly that
line without waiting for a reply. Use `expect()` to observe the next output when
using raw `send()`. An input result of `"prompt"`, `"exited"`, or `"silent"` is
not a CommandResult: silence or a prompt alone never proves authentication or
command success.

For a program within a persistent shell, use this template with its actual
prompt and quit command:

```py
with local.shell("bash") as shell:
    result = shell("hostname", check=True)
    with shell.enter("YOUR_INTERACTIVE_PROGRAM", prompt="NEXT_PROMPT>",
                     exit="quit") as program:
        program.expect("QUESTION:", timeout=10)
        program.input("answer", timeout=10)  # Includes one Enter.
        program.send("partial")             # Includes no Enter.
        program.input("-reply", timeout=10)  # Completes partial-reply.
    result = shell("printf ready", check=True)
```

Equivalent `.spy` operations are `$.input()`, `$.send()`, and `$.expect()` inside
`with $.enter(...)`. Keep `$command` for shell commands. Inside `enter()`, `$...`,
console calls, and `send_line()` retain their existing input dispatch for
compatibility; prefer explicit `input()` for new replies. `send_line()` remains
a command-execution alias in a shell, not a raw line-write helper.

Some password-reading programs use the controlling terminal instead of stdin;
`input=password + "\n"` cannot guarantee a terminal password response. Use an
appropriate PTY and `enter()`/`input()` for terminal conversations. Supply secrets
through `getpass` or a secret manager and avoid verbose output when it may expose
them. For authenticated privilege changes, prefer `su()`/`sudo()`'s handshake.

<a id="unreleased-command-results-and-long-running-programs"></a>

## 4.0: command results and long-running programs

A completed command returns an immutable `CommandResult`, whether called as
`session(command)`, `shell(command)`, a single `$command`, or `$command` inside
`with $.shell()`, `su()`, or `sudo()`. Save `result` and read its named fields,
or unpack exactly `stdout, stderr, exitcode`. This changes the released 3.1.5
console contract: old `stdout, stderr = shell(command)` must be migrated.
Shell calls accept command strings; argv execution belongs to Session.

<!-- example: {"id":"shell-result", "profile":"4.0.2", "stdout":"first 0\n"} -->
```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    with local.shell("bash") as shell:
        result = shell("printf first", check=True)
        shell("printf second", check=True)
    print(result.stdout, result.exitcode)  # Retains the first command.
```

Equivalent `.spy` code:

```spy
result = $hostname
with $.shell("bash"):
    result = $hostname
    stdout, stderr, exitcode = $hostname
```

A shell context scopes lifetime; it does not aggregate command results.
`$.stdout`/`$.stderr` (or `console.stdout`/`stderr`) remain live buffers;
`$.exitcode` is the latest status. Prefer the saved result for completed commands.
A shell `check=True` failure carries `.result`, just like a Session failure.
A timeout is an exception, not a fabricated completed result or proof of a stop.

### Choose the command's lifetime before choosing syntax

| Need | Recommended choice | When a result is available |
| --- | --- | --- |
| A finite command | Session call; use argv for dynamic arguments | On completion |
| A finite capture | Give tcpdump `-c N` and set a total deadline | On completion; `-c N` can still wait forever if no packets arrive |
| Stream until a condition or user Ctrl-C | `Session.start()` with `iter_stdout()` and `stop()` in `finally` | `wait()`/`stop()` returns JobResult; inspect stop reason and termination status |
| Run inside a configured shell or privilege context | `console.enter(command, exit=chr(3))`, `expect()`/live buffers | The body observes live output; leaving requests Ctrl-C and recovers the shell |
| Send input to a REPL or interactive program | `enter()`, then `input()`/`send()`/`expect()` | Input readiness is not a completed command or its exitcode |

Do not assign `result = $tcpdump ...` and expect to inspect it while the command
is running: synchronous assignment waits for completion. Changing two-value
unpacking to three values does not add streaming or a stop condition.
Shell command calls keep their existing completion deadline (60 seconds by
default); use managed jobs for indefinite lifetimes. `start(timeout=None)` means
no total deadline, so the caller must supply a stop condition or handle Ctrl-C.
Prefer a finite fallback deadline for unattended agents, even when they also
stop on output. A loop checking elapsed time only after receiving a chunk cannot
stop a silent process on time; use the job deadline for that guarantee.

### Best practice for tcpdump and other continuous output

Use `tcpdump -l -n -i INTERFACE` for line-buffered text; select the interface and
capture privileges explicitly. For a finite capture, use `-c N` plus a deadline.
For an output condition, accumulate chunks or split complete lines before
matching: `iter_stdout()` yields chunks, not packets or lines. Put `stop()` in
`finally`, so condition matches, exceptions, and KeyboardInterrupt all trigger
cleanup. This credential-free example uses a continuous Python process:

<!-- example: {"id":"stream-condition", "profile":"4.0.2", "stdout":"cancelled confirmed\n"} -->
```python
from contextlib import closing
import sys
from sshscript import Session

with closing(Session()) as local:
    with local.start(
        [sys.executable, "-u", "-c",
         "import time; print('ready'); exec('while True: time.sleep(1)')"],
        timeout=10, stop_timeout=1,
    ) as job:
        seen = ""
        try:
            for chunk in job.iter_stdout():
                seen = (seen + chunk)[-4096:]
                if "ready" in seen:  # Replace with the application's condition.
                    break
        finally:
            result = job.stop()
        print(result.stop_reason, result.termination_status)
```

For local tcpdump replace argv with `["tcpdump", "-l", "-n", "-i", "INTERFACE"]`.
On a connected remote Session use `remote.start(..., get_pty=True)` when Ctrl-C
is the intended stop mechanism. PTYs can merge stderr into stdout; do not
assume independent streams. `stop()` requests termination: remote channel close
alone is not evidence that tcpdump stopped. Handle `termination_status="unknown"`
with a separate host/process check. A deadline raises `CommandTimeoutError`
with partial `error.result`; stop does not turn that timeout into success.

When capture needs the current shell's directory/environment or sudo context
(the following is a template inside an existing `local` Session):

```py
with local.shell("bash") as shell:
    with shell.enter("tcpdump -l -n -i INTERFACE", exit=chr(3)) as capture:
        capture.expect("YOUR_PACKET_PATTERN", timeout=30)
    # Ctrl-C requested on leaving; the parent shell is recovered.
    result = shell("printf capture-scope-ended", check=True)
```

This requires capture permission and a suitable PTY. `expect()` observes the
running program; a match does not mean tcpdump exited. Inside `enter()`, console
calls / `$...` send program input and retain their existing readiness-status
return, rather than CommandResult. Use explicit `input()`/`send()` to make the
intent clear to readers and agents. `exit=chr(3)` sends Ctrl-C, not a universal
kill guarantee; context cleanup may raise when recovery cannot be confirmed.
The following `shell()` result describes that following command, not tcpdump.

Retained job output is bounded and can be truncated; check the truncation flags.
Slow stream consumers can raise `BufferError`. For large or binary captures,
write at the source with tcpdump `-w PATH` and retrieve the file after confirming
capture termination; PTY text streams are unsuitable for a binary pcap.

<a id="unreleased-foreground-jobs-inside-shell-sudo-and-su"></a>

## 4.0: foreground jobs inside shell, sudo and su

Use `console.start(command)` or `$.start(command)` inside a shell/sudo/su context
when output must be observed before completion. It returns `CommandJob`, using
the current Bash console's channel, cwd, environment and identity. It does not
launch through the underlying Session. Ordinary `console(command)` / `$command`
still waits and returns `CommandResult`; no migration is needed for finite commands.

<!-- example: {"id":"console-stream", "profile":"4.0.2", "stdout":"cancelled confirmed\nconsole-alive\n"} -->
```python
from contextlib import closing
import shlex
import sys
from sshscript import Session

with closing(Session()) as local:
    with local.shell("bash") as console:
        command = shlex.join([sys.executable, "-u", "-c",
                              "import time; print('ready'); time.sleep(60)"])
        with console.start(command, timeout=10, stop_timeout=2) as job:
            seen = ""
            try:
                for chunk in job.iter_stdout():
                    seen = (seen + chunk)[-4096:]
                    if "ready" in seen:
                        break
            finally:
                result = job.stop()
            print(result.stop_reason, result.termination_status)
        print(console("printf console-alive", check=True).stdout)
```

For tcpdump, select a permitted interface and use the authenticated context:

```spy
from getpass import getpass

with $.sudo(password=getpass("sudo password: ")):
    with $.start("tcpdump -l -n -i INTERFACE", timeout=30) as job:
        try:
            for chunk in job.iter_stdout():
                print(chunk, end="", flush=True)
        finally:
            result = job.stop()
    result = $hostname
```

The sudo example requires native account policy and capture permissions; the
executable Python example above is credential-free. Use nested `$.su()` /
`$.sudo()` to change identity before starting the job. Direct privilege commands,
background `&`, nohup/disown, and replacing the managing shell with exec are
unsupported. Validation rejects common explicit forms; quoted ampersands are
ordinary data. This is not a sandbox: wrapper scripts, aliases, functions and
programs which detach themselves cannot be completely detected or managed.

Console jobs accept one command string, not argv. Quote dynamic values with
`shlex.join()`; Session.start(argv) remains the choice for an independent process.
Console start has a **60-second total deadline by default**, covering startup,
execution and completion; `timeout=None` explicitly removes that deadline.
Prefer a finite deadline for unattended agents. `stop_timeout` bounds the
separate shell recovery handshake. Capture and stream overflow follow CommandJob.

One console channel has one foreground job. While it is active, other commands,
console output/status access, send/input/expect, clear and nested console entry
raise RuntimeError immediately. Use the job's output/wait/stop methods instead.
User operations on a console job must run on its creating thread; internal I/O
runs in background threads. start() inside enter() is rejected: that context is
program input, not a shell command boundary. Leaving an owning console context
also stops an active job; prefer an explicit job context for clear lifetimes.

Completion fences both output streams, records exit status, and verifies the
original effective UID and Bash PID. stop() sends Ctrl-C only when the channel
has a PTY, then probes that same shell. PTY output can merge stderr into stdout;
this text interface is unsuitable for binary capture. A confirmed recovery
allows the next command. It does not prove detached descendants terminated.
Pipe consoles support finite completion but cannot safely interrupt a running
program; a cancelled pipe job fails and disables the console. Ignored Ctrl-C,
identity mismatch, shell exit or an unresolved recovery also disable it. Runtime
failures expose `.result` with `termination_status="unknown"`; a total deadline
raises CommandTimeoutError with partial output, regardless of check. Never clear
a stored channel failure or treat unknown termination as successful cleanup.

## Lifetime and failure rules

- A root `with Session()` does not close the Session. These examples use
  `contextlib.closing`; it calls `close()` but does not inspect its bool result.
  For strict cleanup reporting, inspect `close_errors` or use `close(strict=True)`;
  preserve any already-propagating exception when reporting cleanup failure.
- Remote Session, shell, and managed-job contexts own their scoped cleanup.
- Legacy one-shot failures wait up to two seconds for their owned command worker
  to finish cleanup. Incomplete or failed cleanup is recorded in exception notes.
- Local managed jobs attempt every stdin/stdout/stderr close even after a signal,
  wait, or another close fails. The original execution error remains primary;
  additional cleanup errors appear in its exception notes. If execution succeeded,
  the first cleanup error is raised with notes for subsequent failures.
  A deadline still raises `CommandTimeoutError`; any stored worker error is its
  cause, and cleanup notes are retained on the timeout exception.
- **4.0:** `close()`/`disconnect()` cannot run while this Session or any
  descendant has an active `shell()`, `su()`, `sudo()`, or `enter()` context.
  They raise `RuntimeError` even with `strict=False`, before changing state or
  cleaning any resource. Leave those contexts first; a function `return`, an
  exception, or a break from an enclosing loop runs their context cleanup.
- After leaving consoles, `close()` permanently disables the Session and closes
  its owned console channels, managed jobs, connections and child Sessions.
  Closing a child does not close its parent. Repeated close calls retain the
  cleanup outcome. Console contexts constructed but never entered are also
  cleaned up and cannot be entered after their Session is closed.
- `closed=True` means new execution, connection, console, script and file/key
  operations are forbidden; it does not prove every resource cleanup succeeded.
  `close()` returns a bool, `close_errors` preserves cleanup failures, and
  `close(strict=True)` raises after cleanup if any operation failed.

- A shell block manages one shell lifetime. It does not aggregate every command's
  success. In 4.0 source, completed shell commands return immutable
  CommandResult snapshots and inherit `check`; interactive prompt input does not.
  Console stdout/stderr properties remain live buffers for expect/input workflows.
- A successful final shell status does not prove every pipeline stage succeeded.
- `Session.start()` keeps job results independent of Session latest-command state.

<a id="unreleased-authenticated-susudo-consoles"></a>

## 4.0: authenticated su/sudo consoles

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

### Interactive usage

These transcripts require a real local account and its authentication policy;
they are manual examples, separate from the credential-free CI examples above.
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

### Failure handling

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

### Platform behavior and custom commands

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
native Ubuntu local/SSH gates now exercise real util-linux su, sudo and PAM,
including failure and recovery. Passing candidate reports are required before
claiming validation; configuring CI alone is not a passing result. BusyBox,
FreeBSD and macOS authentication still require native verification. See `unittest/README.console-authentication.md` in the source checkout
for commands, coverage, and the native-system validation matrix.

## Compatibility forms: read, do not generate

| Old/alternative form | Recommended new code |
| --- | --- |
| `$$command`, `onedollar()`, `twodollars()` | `$command` or `exec_command()`, with explicit shell mode when needed |
| Two-value unpacking of a Session command | A named result or three-value unpacking; 4.0 shell commands now follow the same contract |
| `assert` for command success | `check=True` or an explicit exception |
| Dynamic command built with `shlex.join()` | Pass argv directly; `shlex.join()` remains supported, not deprecated |
| `--check` without a filename for updates | `--check-updates`; reserve `--check file.spy` for syntax validation |

The version-profiled executable examples above run in CI. README quickstart
examples are also checked; native account transcripts require the documented
host prerequisites and are not credential-free examples.
The same source is mirrored into the website; edit this file, then use
`tools/sync_api_guide.py` to refresh the website copy. Additional protocol and
production details remain in the full documentation.

Last Updated: 2026-10-10 17:23:11
