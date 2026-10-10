---
title: "Exceptions and Return Values"
parent: "Reference"
grand_parent: "SSHScript Documentation"
nav_order: 4
permalink: /v3a/reference/exceptions-and-return-values/
---

# Exceptions and Return Values

> **Version scope:** The base command API is available in 3.1.5.
> Managed deadlines and jobs described below are features available in 5.0.0.

This contract describes the source API in both normal Python and `python -O`.
Managed-command additions are marked 4.0; the base result/check API
was introduced in 3.1.5.

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

## Exception matrix

| Failure | Exception |
| --- | --- |
| Wrong argument type | `TypeError` |
| Invalid value, content, or combination | `ValueError` |
| Invalid Session/console/channel lifecycle state | `RuntimeError` |
| Operation on a closed channel/transport | `BrokenPipeError` |
| Channel ends while waiting | `EOFError` |
| SSH command closes without an exit-status message (5.0.0; introduced in 4.0) | `EOFError`; no completed command result |
| Legacy one-shot timeout | `subprocess.TimeoutExpired` locally; original Paramiko/socket timeout remotely |
| Managed command deadline | `CommandTimeoutError`, a `TimeoutError` subclass, with partial `JobResult` |
| Managed streaming queue overflow | `BufferError` |
| su/sudo rejected authentication, requested another password, or required an unsupplied password (4.0) | `PermissionError` |
| su/sudo entry or return deadline expired (4.0) | `TimeoutError` |
| su/sudo early command exit, identity mismatch, or reuse of a single-use context (4.0) | `RuntimeError` |
| Disconnected SFTP access or transfer | `SSHScriptException` |
| Filesystem failure | Appropriate `OSError` subclass |
| SSH/authentication/host-key failure | Original Paramiko exception and traceback |
| Internal AST/data-structure invariant | Descriptive `RuntimeError` |
| Session-stack index outside its bounds | `IndexError`, following deque |

`AssertionError` was never a supported SSHScript API contract. Do not catch it
as input validation. User-written `.spy` assertions remain ordinary Python
assertions and are removed by `python -O`.

Missing SSH exit status is a protocol failure even with `check=False`.
Paramiko's internal `-1` sentinel is not a command exit code. Transport errors
retain their original types rather than becoming `CommandTimeoutError`, and
an SSH failure never causes local execution fallback. See
[the missing-status and transport-loss contract]({{ site.baseurl }}/v3a/concepts/results-and-error-model/#missing-ssh-exit-status-and-transport-loss-400dev0-unreleased).

<a id="authenticated-console-entry-unreleased"></a>

## Authenticated console entry (4.0)

A failed su/sudo entry never silently falls back to the original account or
resends the same password. I/O errors propagate; invalid `enter_timeout` types
raise `TypeError`, and invalid numeric values raise `ValueError`. A separate
two-second recovery attempt verifies return to the original parent shell.
Unconfirmed recovery makes the channel reject subsequent commands. Handle
entry errors outside the `with` statement and create a new context for retries.
See [the authenticated console contract]({{ site.baseurl }}/v3a/reference/session-and-console-api/#authenticated-susudo-entry-unreleased).

## Results and failure handling

`Session.exec_command()` returns an immutable `CommandResult`. Unpack three
values: `stdout, stderr, exitcode = result`. Output is captured text. The result
also has `host`, `duration`, and `command`; `session.last_result` retains it.
Saved results survive subsequent commands and Session closure.

With `check=False` (the default), nonzero status remains data. With `check=True`,
local and remote one-shot commands raise `subprocess.CalledProcessError` after
saving the result. The exception carries text `stdout`/`stderr` and `result`.

```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as session:
    stdout, stderr, exitcode = session.exec_command(["false"])
    if exitcode != 0:
        raise RuntimeError(f"command failed: exitcode={exitcode}")
```

In 4.0 source, completed shell/su/sudo commands also return immutable
CommandResult snapshots, and check failures carry `.result`. Published 3.1.5
console calls still return two buffers. Interactive input reports
prompt/exit/silence instead of a command result.
Transfers return paths without updating command status. `close()` returns a
success bool and records `close_errors`; `close(strict=True)` raises after
attempting cleanup. Do not depend on `assert` for production failure handling.

See [Results and Error Model](../../concepts/results-and-error-model/) for field
semantics and migration from live output to text snapshots.

## Validation guarantees

One-shot commands accept nonempty strings or nonempty lists/tuples of strings.
Argv disallows an empty executable, NUL, and shell mode. Persistent commands
must be one-line strings;
`get_pty` must be None/bool, and internal `for_with` must be bool. Compiled bytes
regexes are rejected by text matching. Appended output must be str. Invalid
inputs are rejected before command execution or affected buffer mutation.
Failed listener removal, duplicate hijack/release, and last-layer removal do
not alter their associated state.

See [Session and Console API Reference](../session-and-console-api/) for
operation signatures and cleanup details.

Last Updated: 2026-10-10 19:43:07
