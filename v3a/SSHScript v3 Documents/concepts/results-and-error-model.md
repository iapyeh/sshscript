---
title: "Results and Error Model"
parent: "Concepts"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
permalink: /v3a/concepts/results-and-error-model/
---

# Results and Error Model

> **Version scope:** The base command API is available in 3.1.5.
> Managed deadlines and jobs described below are features available in 4.0.1.

A completed command, an API failure, and cleanup failure are different outcomes.

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

## Command results

One-shot Session calls return an immutable `CommandResult`:

```python
result = session.exec_command(["printf", "%s", "hello"], check=True)
stdout, stderr, exitcode = result
print(result.stdout, result.stderr, result.exitcode)
```

Unpacking, indexing, slicing, and `tuple(result)` use exactly three values in
that order. `len(result)` is 3. Two-value unpacking must be changed.
`stdout` and `stderr` are text snapshots, not live buffers. Saved results remain
valid after another command or after the Session closes.

| Field | Meaning |
| --- | --- |
| `stdout`, `stderr` | Captured text output. |
| `exitcode` | This command's exit status. |
| `host` | Snapshot of `session.host`, or `None` locally; no `hostname` command is run. With SSH config it is the resolved HostName. |
| `duration` | Monotonic elapsed seconds from command execution through output collection and worker cleanup; includes transport waiting, excludes prior connection setup. |
| `command` | Normalized command string or immutable argv tuple. |

`session.last_result` holds the latest completed one-shot result. Starting a
command clears it until completion; validation failures leave it unchanged.
The existing `session.stdout`/`stderr` properties still expose the underlying
buffers, while `session.exitcode` reflects the latest command.

Nonzero status is data by default. Both local and remote one-shot commands
accept `check=True`; this raises `subprocess.CalledProcessError` after saving
the output and status. Its `stdout`/`stderr` are text, `cmd` is the normalized
command, and `result` is the full snapshot. Transport and timeout errors keep
their original exception types. No complete result is promised for those errors.

In 4.0 source, completed shell/su/sudo commands return the same immutable
CommandResult as one-shot commands. Published 3.1.5 console calls still return
two live buffers. Interactive input returns prompt, exit, or silence status;
a prompt is readiness for input, not process completion.

<a id="missing-ssh-exit-status-and-transport-loss-400dev0-unreleased"></a>

## Missing SSH exit status and transport loss (4.0.1, 4.0)

If an SSH command channel closes without an exit-status message, both legacy
and managed one-shot calls raise `EOFError`. Paramiko's internal `-1` sentinel
is not a reported command status and is not returned as a completed result or
converted into `CalledProcessError`. This failure applies with either value of
`check`; no completed one-shot result is saved.

A transport failure after output has arrived remains a transport failure, not
a command deadline. Managed jobs retain observed output in `job.stdout` and
`job.stderr`; output alone does not establish completion. SSHScript does not
retry the command on the local host. Closing the owned command channel does
not require closing an otherwise usable shared SSH transport, and does not
prove that the remote process stopped. See
[Contributing and Testing]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/development-and-testing/)
for the transport and resource boundary tests.

## A shell block has a lifetime, not an aggregate success result

The entire `with $.shell()` block can be viewed as one shell process's lifetime:
start the shell, perform several operations in it, then leave and clean up.
Within that lifetime, each command has its own outcome. The context manager
does not collect those outcomes into one `CommandResult` or automatically fail
the block when any command returns nonzero.

Keep these three questions separate:

| Question | Meaning |
| --- | --- |
| Has the shell scope ended? | The context manager is leaving and performing cleanup. This does not validate every command. |
| Has this command or interaction returned? | The console's command-completion or prompt/wait rules were satisfied. A REPL prompt means readiness, not process exit. |
| Did the workflow succeed? | The application checked each required step and any relevant postconditions. |

For example, this `.spy` block records a failure followed by a success:

```python
with $.shell("bash") as console:
    $false
    failed_status = console.exitcode
    $echo continued
    last_status = console.exitcode

print(failed_status, last_status)  # 1 0
```

The final command's status, or the shell process's eventual exit status, is
not a history of all preceding commands. Even a one-shot shell string with
several commands follows the shell's status rules: `check=True` checks the
reported status, not every statement in the string. Cleanup failures and
Python exceptions can still make a shell block raise; that is distinct from
automatically checking command exit codes.

## Check each required console command and save its output

**4.0 source:** save the returned result rather than retaining a live
buffer or reading status after another command has replaced it. Use `check=True`
for required commands; a failure carries its immutable `.result`.

```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    with local.shell("bash") as console:
        console("cd /tmp", check=True)
        saved = console("pwd", check=True)
        console("printf next", check=True)
    print(saved.stdout.strip())
```

`console.stdout`/`stderr` remain live buffers for interaction. Inside `enter()`,
use `input()`/`send()`/`expect()`; an input call is not a completed process result.
For tcpdump, choose bounded capture, managed streaming with explicit stop, or an
enter() scope with Ctrl-C cleanup. See the
[canonical command guide]({{ site.baseurl }}/v3a/recommended-api/#unreleased-command-results-and-long-running-programs).
Do not depend on `assert` for production failure handling.

A pipeline or compound command still needs a shell-specific success policy
when its individual stages matter; checking its final status alone cannot
supply that policy. For reusable work that needs no shared shell state,
prefer one-shot Session calls with `check=True` and saved CommandResult objects.
For a single long-running process, use the managed job interface above;
it provides a separate running-job lifetime rather than a synchronous console call.

## Exceptions

Wrong types raise TypeError; invalid values raise ValueError. Invalid lifecycle
transitions raise RuntimeError. Closed operations raise BrokenPipeError, ended
waits raise EOFError, and timeouts raise TimeoutError. Disconnected SFTP access
raises SSHScriptException. Original filesystem and Paramiko errors propagate.
The complete matrix is in [Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

Runtime validation remains active under `python -O`. User assertions are
removed by optimized Python; production scripts must use explicit result
checks. AssertionError was never a supported package validation contract.

## Cleanup and transfers

Transfers return paths and do not update command exitcode. Cleanup reports
failures through `close_errors` and the bool returned by `close()`;
`close(strict=True)` raises after cleanup. Preserve the primary operation
exception when reporting a cleanup failure. High-level automatic cleanup does
not replace an application's explicit cleanup reporting policy.

See [Failure Model and Production Checklist](../../security-and-operations/failure-model-and-production-checklist/)
for production handling patterns.

Last Updated: 2026-10-08 23:48:09
