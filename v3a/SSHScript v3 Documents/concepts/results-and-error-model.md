---
title: "Results and Error Model"
parent: "Concepts"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
permalink: /v3a/concepts/results-and-error-model/
---

# Results and Error Model

> **Next-release API:** This page describes the updated source checkout.
> The published 3.1.4 wheel retains the earlier command/config/check behavior.

A completed command, an API failure, and cleanup failure are different outcomes.

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

Persistent console commands are a separate API: they return two live buffers
and expose status through `console.exitcode`. Interactive input returns prompt,
exit, or silence status. Neither should be treated as a one-shot CommandResult.

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

Last Updated: 2026-09-26 16:11:31
