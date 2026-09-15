---
title: "Streaming Output"
parent: "Advanced Session API"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 4
---

# Streaming Output

Long-running programs can produce output well before they exit.
`Session.enter()` exposes that output as it arrives, so Python can process a
log follower, monitor, backup tool, or packet capture incrementally.

## Stream output

```python
from sshscript import Session

session = Session()
try:
    with session.enter("ping -c 4 example.net") as process:
        for line in process.stdout(10):
            print(line, end="")
finally:
    session.close(strict=True)
```

`process.stdout(10)` returns an iterator. It yields received stdout chunks,
normally lines, and resets its ten-second timer whenever new output arrives.
If nothing new arrives before the timeout, it raises `TimeoutError`.

For a continuous command, supply an exit action:

```python
with session.enter(
    "tail -F /var/log/syslog",
    exit=chr(3),
) as process:
    for line in process.stdout(30):
        if "ERROR" in line:
            print("alert:", line, end="")
```

`exit=chr(3)` sends Ctrl-C when the interactive context ends.

## Stop on a condition

```python
matches = 0

with session.enter(
    "tail -F /var/log/myapp.log",
    exit=chr(3),
) as process:
    for line in process.stdout(60):
        if "completed" in line:
            matches += 1
        if matches == 10:
            break
```

Leaving the context after `break` sends the configured exit action. An
intentionally endless command should always have an exit action or another
well-defined termination mechanism.

## Iterator options

```python
process.stdout(timeout=None, silent=False, shift=True)
```

| Argument | Behavior |
| --- | --- |
| `timeout` | Seconds to wait after the last output; `None` waits indefinitely. |
| `silent` | If `False`, inactivity raises `TimeoutError`. If `True`, iteration ends normally. |
| `shift` | If `True`, yielded chunks leave the live buffer. If `False`, the buffer is retained. |

Treat unexpected silence as an error:

```python
try:
    with session.enter(
        "tcpdump -n -i eth0",
        exit=chr(3),
    ) as process:
        for line in process.stdout(15):
            process_packet(line)
except TimeoutError as exc:
    raise RuntimeError(
        "tcpdump produced no output for 15 seconds"
    ) from exc
```

For an expected quiet interval, use `silent=True`:

```python
with session.enter(
    "./wait-for-work.sh",
    exit=chr(3),
) as process:
    for line in process.stdout(5, silent=True):
        print(line, end="")
```

## Preserve accumulated output

Iteration consumes output by default. Use `shift=False` when the complete
buffer is needed afterward:

```python
with session.enter(
    "./progressive-report.sh",
    exit=chr(3),
) as process:
    for line in process.stdout(20, shift=False):
        print(line, end="")
        if "DONE" in line:
            break

    report = str(process.stdout)
```

Keep the consuming default for unbounded streams so processed output does not
accumulate indefinitely.

## Remote and privileged streams

```python
with local.connect("ops@example.net") as remote:
    with remote.sudo(password=password) as root:
        with root.enter(
            "journalctl -f -u nginx",
            exit=chr(3),
        ) as process:
            for line in process.stdout(30):
                if "error" in line.lower():
                    print(line, end="")
```

The output-handling code is the same for local, remote, nested, and
privileged Sessions.

## Optional Dollar syntax

```python
with $.enter("journalctl -f -u nginx", exit=chr(3)):
    for line in $.stdout(30):
        if "error" in line.lower():
            print(line, end="")
```

Last Updated: 2026-09-14 18:02:02
