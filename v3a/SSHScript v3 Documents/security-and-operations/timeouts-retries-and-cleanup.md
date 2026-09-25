---
title: "Timeouts, Retries, and Cleanup"
parent: "Security and Operations"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
permalink: /v3a/security-and-operations/timeouts-retries-and-cleanup/
---

# Timeouts, Retries, and Cleanup

Reliable automation bounds every wait, retries only operations whose outcome is
known, and makes cleanup failure observable. A single `timeout=` value cannot
cover all three concerns because connection setup, command execution,
interactive protocols, and the whole workflow have different clocks.

## Select a timeout for each layer

| Layer | SSHScript or backend control | Meaning |
| --- | --- | --- |
| TCP connection | `connect(timeout=...)` | Paramiko socket connection timeout. |
| SSH banner | `connect(banner_timeout=...)` | Maximum wait for the SSH protocol banner. |
| Authentication | `connect(auth_timeout=...)` | Maximum wait for authentication response. |
| Local one-shot command | `exec_command(..., timeout=...)` | `subprocess.run()` wall-clock timeout. |
| Remote one-shot command | `exec_command(..., timeout=...)` | Paramiko channel I/O timeout, not a total command deadline. |
| Interactive prompt or response | Console `expect()`/input timeout | Bound for that protocol state. |
| Streaming output | `wait_for_output()` or `wait_for_silent()` | Output or silence bound, not necessarily process completion. |
| Entire workflow | Application supervisor | End-to-end deadline and cancellation policy. |

Always pass connection limits explicitly. Direct connections do not invent a
site-appropriate timeout for you:

```python
with local.connect(
    "ops@example.net",
    timeout=10,
    banner_timeout=10,
    auth_timeout=10,
) as remote:
    stdout, stderr = remote.exec_command(
        "systemctl is-active nginx",
        shell=False,
        timeout=20,
    )
```

`proxyCommand` connections default these three connection-stage limits to 30
seconds unless overridden. Use explicit values anyway so the operational
policy is visible at the call site.

## Local and remote command timeouts differ

A local one-shot timeout raises `subprocess.TimeoutExpired`:

```python
import subprocess


try:
    local.exec_command("long-running-tool", shell=False, timeout=15)
except subprocess.TimeoutExpired:
    handle_local_timeout()
```

`subprocess.run()` terminates and waits for its direct child, but separately
spawned descendants or external state may still require reconciliation.

A remote `timeout=` configures channel I/O. It does not prove that the remote
program was killed, and a program that keeps producing data can exceed the
number of wall-clock seconds supplied. When a total remote deadline matters,
use a server-side job protocol or supervisor with a durable job identifier.
After a disconnect or deadline, query that identifier before deciding whether
to submit the work again.

## Model interactive work as states

An interactive session is a protocol, not a sequence of blind sleeps. For each
state, define:

- the exact prompt or output pattern that proves readiness;
- a finite timeout;
- the input sent after that match;
- the expected exit condition; and
- what an early EOF or changed prompt means.

Use the narrowest stable regex. Test wrong credentials, unexpected prompts,
early exit, timeout, and PTY behavior. A PTY can merge stderr into stdout and
introduce carriage returns or terminal control sequences, so validate the
actual target application. See
[Interactive Programs with `Session.enter()`]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/Advanced/enter/).

For a long-running stream, an output-silence limit answers only whether new
data arrived. It does not establish that a silent process is dead. Combine the
silence policy with a protocol-specific health check and an overall workflow
deadline. See
[Streaming and Looping Output]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/Advanced/looping-output/).

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

## Production checklist

- [ ] Connection, banner, and authentication timeouts are explicit.
- [ ] Local command and interactive waits have finite bounds.
- [ ] Remote total deadlines are enforced outside the channel I/O timeout.
- [ ] Silence is not treated as proof of process termination.
- [ ] Retried operations are idempotent or reconciled before another attempt.
- [ ] Attempts, backoff, jitter, and total workflow duration are bounded.
- [ ] Broken transports are discarded rather than reused.
- [ ] Every remote Session and console has a clear owner and scope.
- [ ] Root Sessions are closed and `close_errors` is reported safely.
- [ ] Cleanup failure cannot replace an already propagating primary failure.

See [Runtime Troubleshooting](../runtime-troubleshooting/) for symptom-based
diagnosis and the
[Failure Model and Production Checklist](../failure-model-and-production-checklist/)
for the release review gate.

Last Updated: 2026-09-25 16:37:52
