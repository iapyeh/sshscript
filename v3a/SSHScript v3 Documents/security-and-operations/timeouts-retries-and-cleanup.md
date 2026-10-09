---
title: "Timeouts, Cancellation, and Cleanup"
parent: "Security and Operations"
grand_parent: "SSHScript Documentation"
nav_order: 3
permalink: /v3a/security-and-operations/timeouts-retries-and-cleanup/
---

# Timeouts, Cancellation, and Cleanup

> **4.0 source API:** `Session.start()`, `command_timeout`,
> `CommandJob`, `JobResult`, and `CommandTimeoutError` are features available in 4.0.2.
> They are not available in the published 3.1.5 package.

## Design: a deadline and a stop request are independent

A short command normally finishes itself. A capture tool such as tcpdump can
legitimately run until its user stops it. Neither needs a different transport
API: a managed command can have a finite total budget or `timeout=None`, and
both can be cancelled with `stop()`.

A deadline bounds how long SSHScript waits for the command. It does **not**
guarantee that a remote process has been terminated. Cancellation has two
observable outcomes: `confirmed` means the direct local child was reaped or a
remote exit status was received; `unknown` means termination was not confirmed.
Neither result proves that detached descendants have stopped or that side
effects were rolled back.

## Choose the appropriate API

| API | Time limit and result |
| --- | --- |
| `session.exec_command(cmd, command_timeout=30)` | New managed path: one 30-second budget on local and SSH backends; returns `JobResult`, a `CommandResult` subclass. |
| `session.exec_command(cmd, command_timeout=None)` | Managed path without an execution deadline; Ctrl-C unwinds the call and triggers bounded cleanup. |
| `session.start(cmd, timeout=30)` | Returns a `CommandJob` immediately; the same total budget continues even when nobody calls `wait()`. |
| `session.start(cmd, timeout=None)` | No execution deadline; use `stop()` or leave the job's `with` block. |
| `session.exec_command(cmd, timeout=30)` | Legacy behavior: local subprocess timeout, remote Paramiko channel timeout. Preserved for 3.x compatibility. |
| `connect(timeout=..., banner_timeout=..., auth_timeout=...)` | Separate connection-stage limits; unchanged. |

Do not specify both `timeout` and `command_timeout` to `exec_command()`.
Explicit `command_timeout=None` selects managed execution; omitting the
argument leaves the legacy path unchanged. There is no new `io_timeout` or
`idle_timeout` option in this implementation. Persistent `shell()`/`enter()`
consoles retain their existing prompt and waiting contracts.

## Long commands in a persistent shell

Completed shell commands now return immutable three-value CommandResult
snapshots in 4.0 source. This does not change streaming/interaction:
`result = console("tcpdump ...")` waits for completion. Use `start()` for a
separate managed process, `console.start(command, timeout=30)` for a foreground
job in the current Bash shell/sudo/su context, or `console.enter(..., exit=chr(3))` with expect/send
when the current shell or privilege context is required. Neither stopping on
an output match nor reaching a prompt proves process termination. For unattended
agents use a finite fallback deadline; an elapsed-time check inside a stream loop
cannot bound a silent process. `tcpdump -c N` also needs a deadline when packets
might never arrive. See the
[choices and runnable best-practice example]({{ site.baseurl }}/v3a/recommended-api/#unreleased-command-results-and-long-running-programs).

## One total budget, not a timer reset by output

The managed clock uses monotonic time and begins after option validation,
before command startup. It includes process/channel creation, the SSH exec
request, stdin delivery, stdout/stderr collection, and waiting for completion.
It excludes an already completed `connect()` call. Completion requires an exit
status and the end of output, not simply the first output or an exit-status
notification. Continuous output does not extend the deadline.

Finite time values must be positive numbers; zero, negatives, bools, infinity,
and NaN are rejected. `None` disables only the execution deadline.

On expiry, SSHScript requests cancellation and allows `stop_timeout` seconds
(default 3) for graceful shutdown, followed by forced cleanup and up to one
additional second of worker waiting. Scheduling and process creation can add
latency: this is not a hard real-time return guarantee. A late-created local
process is killed; a late-opened SSH channel is closed. A backend that remains
stuck cannot be reported as confirmed terminated.

```python
from contextlib import closing
from sshscript import Session, CommandTimeoutError

with closing(Session()) as local:
    try:
        result = local.exec_command(
            ["sleep", "60"],
            command_timeout=2,
            stop_timeout=1,
            check=True,
        )
    except CommandTimeoutError as exc:
        print("Deadline expired:", exc.elapsed)
        print("Termination:", exc.termination_status)
        print("Partial stdout:", exc.stdout)
```

`CommandTimeoutError` inherits `TimeoutError` and exposes `command`, `host`,
`timeout`, `elapsed`, text `stdout`/`stderr`, `termination_status`, and `result`.
The result is a partial `JobResult`; its `exitcode` is `None` when unavailable.
Timeout raises even with `check=False`. Other startup/transport errors remain
errors. Natural nonzero exits with `check=True` raise `CalledProcessError`
with a `result` attribute. Deliberate user cancellation does not turn a signal
exit into a `check=True` failure.

## Streaming tcpdump until Ctrl-C

Use an account already authorized to capture traffic. The example captures
text output and runs tcpdump directly; it does not handle interactive sudo
passwords. Where site policy permits, an explicit `sudo -n` prefix can be used,
but that adds another program to the termination path and must be tested.

```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    with local.connect(
        "ops@example.net", timeout=10, banner_timeout=10, auth_timeout=10
    ) as remote:
        with remote.start(
            ["tcpdump", "-l", "-n", "-i", "eth0"],
            timeout=None,
            stop_timeout=5,
            get_pty=True,
            check=True,
        ) as capture:
            try:
                for chunk in capture.iter_stdout():
                    print(chunk, end="", flush=True)
            except KeyboardInterrupt:
                # Ctrl-C ends the capture, not a command-timeout failure.
                pass
            finally:
                result = capture.stop()

            print("\nStop reason:", result.stop_reason)
            print("Termination:", result.termination_status)
            if result.termination_status == "unknown":
                print("Verify the remote capture process before starting another.")
```

A PTY lets `stop()` attempt to send Ctrl-C to the remote foreground job.
This depends on the terminal's signal settings and the foreground application;
it is not a general SSH signal-delivery guarantee. A PTY can merge stderr into
stdout and change line endings. If the program does not exit within
`stop_timeout`, SSHScript closes this command's channel and returns `unknown`
unless it observed an exit status. The shared SSH transport remains open.
Without a PTY, remote `stop()` closes the channel immediately and does not
claim that the remote process was killed. Reliable non-PTY remote termination
requires an external supervisor or an application-specific control protocol.

For local tcpdump, use `local.start([...], timeout=None)` without `get_pty`.
Managed local jobs have a dedicated process group: `stop()` sends SIGINT, then
SIGKILL after the grace period if needed, and reaps the direct child. Programs
can use SIGINT to flush capture data and print statistics. Descendants that
escape the process group are not covered. Local managed PTYs are not supported;
use `Session.enter()` for local interactive terminal programs.

For a programmatic stop, call `capture.stop()` from the controlling code or
another thread. `wait()` and `stop()` return the same snapshot on repeated
calls. A deadline that already expired still raises `CommandTimeoutError`.
Leaving a job context stops a running job; cleanup errors do not replace an
exception already propagating from the block. `Session.close()` also stops
active managed jobs before closing their transport and reports unconfirmed
termination through its cleanup reporting contract.

## Bounded output and result ownership

Managed jobs retain the last `capture_limit` bytes per stream (default 1 MiB).
`JobResult.stdout_truncated` and `stderr_truncated` indicate discarded history.
`capture_limit=0` disables retained output but does not disable streaming.
Output is decoded as UTF-8 with replacement for invalid or truncated sequences.
Unlike the legacy execution path, capture is bounded even for a days-long job.

`iter_stdout()` yields text **chunks**, not necessarily complete lines. Use one
consumer per job. Its queue holds 128 chunks of at most 8192 bytes each. If a
consumer falls behind, it raises `BufferError`; `dropped_stdout_chunks` records
loss. Both stdout and stderr are drained even without an iterator. For lossless
large captures, write to a file at the command source (for example tcpdump's
`-w` option), then transfer that file; do not send binary pcap through a PTY or
the text iterator. The current API does not provide a stderr iterator.

`start()` leaves Session's latest-command fields unchanged: each concurrent job
owns its output and result. `exec_command(command_timeout=...)` sets
`session.last_result` after normal completion (including `check=True` failures),
and exposes text tails through `session.stdout`/`stderr`. On timeout,
`last_result` remains `None`; use the exception's partial result. `JobResult`
adds `stop_reason` (`completed`, `cancelled`, `timeout`), `termination_status`,
and truncation flags while retaining three-value unpacking.

## Retry only a known-safe boundary

Do not wrap an entire deployment in a generic retry decorator. Classify the
failure and the operation first.

A bounded retry can be appropriate for connection establishment when the
failure proves that no command was dispatched. The caller must choose the
exception set for its network and stop immediately for authentication,
host-key, validation, or policy failures:

```python
import random
import time


def connect_with_backoff(local, target, retryable, attempts=3):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return local.connect(
                target,
                timeout=10,
                banner_timeout=10,
                auth_timeout=10,
            )
        except retryable as exc:
            last_error = exc
            if attempt == attempts:
                break
            delay = min(8.0, 0.5 * (2 ** (attempt - 1)))
            time.sleep(delay + random.uniform(0, delay / 4))
    raise last_error
```

Pass a deliberately narrow tuple such as the connection-timeout/refusal types
that your environment has tested. Do not include Paramiko authentication or
bad-host-key exceptions. Do not use this pattern after command dispatch.

Before retrying a state-changing operation, answer all of these questions:

1. Is the operation idempotent or protected by a transaction?
2. Is it certain that the previous attempt never reached the target?
3. Can the target be queried using a stable correlation or job identifier?
4. Is the retry bounded by both an attempt count and an overall deadline?
5. Will a new verified Session be used instead of a broken transport?

If the previous outcome is ambiguous, reconcile target state first. Prefer
convergent operations ("ensure this state") to repeated imperative changes
("add one more").

## Close resources without hiding the primary failure

Remote Session and console context managers close their owned resources on
scope exit. A remote Session cleanup failure is raised after an otherwise
successful block; if the block is already propagating an exception, SSHScript
keeps that exception primary and adds a cleanup note.

A root local Session remains reusable after leaving `with session:` and must be
closed explicitly. `close()` attempts every cleanup step, returns `False` when
any step failed, and stores `(operation, exception)` pairs in `close_errors`.
`close(strict=True)` raises `RuntimeError` after all attempts.

```python
from sshscript import Session


local = Session()
try:
    perform_work(local)
except BaseException as primary:
    if not local.close():
        operations = ", ".join(
            operation for operation, _ in local.close_errors
        )
        primary.add_note(
            f"SSHScript cleanup also failed in: {operations}"
        )
    raise
else:
    local.close(strict=True)
```

Log only sanitized operation names and exception types unless an exception has
been reviewed for secrets. Repeated `close()` calls preserve the same result;
they do not erase an earlier cleanup failure.

`run_file()` and `run_script()` apply the same preservation rule to ordinary
execution exceptions. Cleanup failure raises after successful execution and is
attached as a note when ordinary script execution already failed. A cleanup
failure overrides `$.exit()` or `$.break()` control status so incomplete
cleanup cannot be reported as the requested status.

## Verification cases

Tests cover silent and continuously writing commands, blocked stdin, large
stderr, an SSH exec request that never acknowledges, graceful SIGINT handling,
forced local termination, bounded capture, slow consumers, and explicit unknown
remote cancellation. Credential-free SSH tests use real Paramiko transports
over a socket pair; CI also exercises managed commands against OpenSSH.

<a id="susudo-entry-deadlines-and-retries-unreleased"></a>

## su/sudo entry deadlines and retries (4.0)

`Session.su()`, `Session.sudo()`, and nested console equivalents accept
`enter_timeout=10` in 4.0 source. Use a larger positive finite value
when PAM or shell startup takes longer. This is separate from command and SSH
connection timeouts. The shared entry deadline starts in `__enter__` and covers
lock acquisition, authentication, target-shell readiness, and `initials`;
factory-time base-shell creation and `console_info` probes are outside it.
The same duration bounds return to the parent during normal context exit.

Readiness requires a fresh success marker plus effective UID and shell PID
checks. `wait_for_silent(1)`, absence of a repeated password prompt, and absence
of an error message cannot prove authentication succeeded. A timeout means
readiness was not confirmed; it does not establish that the password was wrong.

The password is sent at most once. A rejection or second password request
raises `PermissionError`; there is no automatic retry. Handle entry failures
outside the `with` block, whose body runs only after readiness is confirmed.
Failure recovery has its own two-second budget. The parent shell must be
verified before reuse; otherwise the channel is marked failed and refuses
further commands. Direct `shell=False` entry has no parent and its owning
context closes the channel on failure. Resource cleanup may take additional
time. `console.closed` alone is not proof of successful recovery.

Create a new su/sudo context for an explicit retry; each context is single-use.
If the old channel is unusable, create a new underlying channel. See the
[authenticated entry contract]({{ site.baseurl }}/v3a/reference/session-and-console-api/#authenticated-susudo-entry-unreleased)
for manual examples, exception types, and platform requirements.

<a id="unreleased-console-job-deadlines-and-recovery"></a>

## 4.0 console job deadlines and recovery

console.start() defaults to a 60-second total budget, unlike Session.start()
which defaults to no deadline. Supply a finite timeout for unattended agents.
stop_timeout separately bounds recovery. A PTY job requests Ctrl-C, then verifies
its original UID/PID and readiness; pipe cancellation cannot safely interrupt.
Failure to recover disables the console. Job errors carry partial `.result`;
deadlines raise CommandTimeoutError even with check=False. No further command
is accepted while the job is active. PTY output may merge streams. Native
su/sudo validation remains environment-specific; protocol fixtures are not proof
of all PAM/sudoers compatibility. See [console foreground jobs]({{ site.baseurl }}/v3a/recommended-api/#unreleased-foreground-jobs-inside-shell-sudo-and-su).

Last Updated: 2026-10-09 10:40:03
