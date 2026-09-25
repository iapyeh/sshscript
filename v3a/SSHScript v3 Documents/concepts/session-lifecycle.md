---
title: "Session Lifecycle"
parent: "Concepts"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
permalink: /v3a/concepts/session-lifecycle/
---

# Session Lifecycle

A `Session` owns an execution endpoint and can also be the active context used
by Dollar syntax. These roles are related but distinct: activation selects
where transformed commands run; ownership determines who must close the
resource.

## Lifecycle at a glance

| Object | Created by | Where commands run | What ends its lifetime |
| --- | --- | --- | --- |
| Local Session | `Session()` | Localhost | Explicit `close()` |
| Remote child Session | `session.connect(...)` | SSH host | Its final Session-context exit or explicit `close()` |
| Persistent console | `shell()`, `su()`, `sudo()`, or `enter()` | Existing Session endpoint | The outermost console-context exit |

A local Session remains reusable after leaving `with session:`. A remote
Session closes when its last active Session context exits.

## Own the root, scope the children

```python
from sshscript import Session


local = Session()
try:
    stdout, stderr = local.exec_command("hostname", shell=False)
    print(str(stdout).strip())

    with local.connect(
        "ops@example.net",
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
    ) as remote:
        stdout, stderr = remote.exec_command("uname -s", shell=False)
        print(str(stdout).strip())
except BaseException as primary:
    if not local.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    local.close(strict=True)
```

`connect()` returns a child owned by its parent. Closing a parent recursively
attempts to close connected children in reverse creation order.

Nested connections use the connected parent as a jump host:

```python
local = Session()
try:
    with local.connect("ops@bastion.example.net") as bastion:
        with bastion.connect("db@database.internal") as database:
            database.exec_command("hostname", shell=False)
except BaseException as primary:
    if not local.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    local.close(strict=True)
```

Each child remains a separate Session with its own host identity, results, and
lifetime.

## Activation is not cleanup

Dollar syntax resolves through the active Session or console on the current
thread. A Session is activated temporarily by:

- `with session:`;
- `session.run(source)` while that source executes;
- a transformed `with $.connect(...):` block; or
- a console context such as `$.shell()` or `$.enter()`.

`Session.run()` does not close an existing Session:

```python
remote = local.connect("ops@example.net")
try:
    namespace = remote.run(
        "$hostname\n"
        "remote_name = $.stdout.strip()\n"
    )
    print(namespace["remote_name"])
except BaseException as primary:
    if not remote.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    remote.close(strict=True)
```

Leaving a local activation also does not close it:

```python
local = Session()

with local:
    pass

assert not local.closed
local.close(strict=True)
```

Therefore, do not treat `with Session() as local:` as automatic root cleanup.

## Prefer scoped `.spy` connections

```python
with $.connect("ops@example.net"):
    $hostname
    print($.stdout.strip())
```

The previous active Session is restored at block exit, and the remote child is
closed when its final Session context exits.

For compatibility, an unscoped `$.connect(...)` is transformed into an
activated connection that remains on the current thread's SSHScript stack
until it is closed. Its ownership is harder to see, so avoid that form in new
programs.

## Console lifetime

A persistent console has a scope inside its Session:

```python
local = Session()
try:
    with local.shell() as shell:
        shell.exec_command("cd /tmp")
        stdout, stderr = shell.exec_command("pwd")
        print(str(stdout).strip())
except BaseException as primary:
    if not local.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    local.close(strict=True)
```

The outermost console context owns and closes its channel. Nested `su()`,
`sudo()`, `enter()`, and shell layers can share the channel. Exiting an inner
layer restores the preceding console; exiting the outermost layer closes the
channel.

Keep console scopes inside their Session scope and never use a console after
its `with` block.

## Threads and active contexts

Transformed `.spy` code recognizes normal `threading.Thread(...)` construction
and gives the worker a snapshot of the caller's active SSHScript stack. The
snapshot contains references to the same Session objects; it does not clone
connections.

```python
import threading


def check_host():
    $hostname
    print($.stdout.strip())


with $.connect("ops@example.net"):
    worker = threading.Thread(target=check_host)
    worker.start()
    worker.join()
```

Join workers before leaving the scope that owns the Session. Worker cleanup
does not close inherited Sessions. Because the same Session also has mutable
latest-result state, do not present shared concurrent command execution as
generally race-free.

Ordinary `.py` code is not transformed and its threads do not implicitly
inherit an SSHScript context. Pass a Session explicitly or create and close one
inside each worker.

## Observe cleanup failures

`close()` is idempotent and performs best-effort cleanup:

```python
if not session.close():
    for operation, error in session.close_errors:
        print(operation, type(error).__name__)
```

It attempts remaining cleanup after an individual failure, records
`(operation, exception)` pairs, and returns `False` when any step failed.
Repeated calls retain the same outcome.

```python
session.close(strict=True)
```

Strict close completes all cleanup attempts and then raises `RuntimeError` when
any failed.

A remote Session context uses strict cleanup automatically. After a successful
block, cleanup failure raises. If the block is already propagating an
exception, SSHScript keeps that exception primary and adds a cleanup note.
`run_file()` and `run_script()` do the same for ordinary execution
exceptions on the fresh local root they create. A cleanup failure deliberately
overrides a requested `$.exit()` or `$.break()` control status rather than
reporting that requested status with incomplete cleanup.

Do not rely on garbage collection to report cleanup failure. See the
[Session and Console API Reference](../../reference/session-and-console-api/)
for the normative contract and
[Timeouts, Retries, and Cleanup](../../security-and-operations/timeouts-retries-and-cleanup/)
for production patterns.

Last Updated: 2026-09-25 16:37:52
