---
title: "Streaming and Looping Output"
parent: "How-to Guides"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 7
---

# Streaming and Looping Output

Long-running programs can produce output well before they exit.
`Session.enter()` exposes that output as it arrives, so Python can process a
log follower, monitor, backup tool, or packet capture incrementally.

## Choosing live interaction or a completed result

Completed shell commands return immutable CommandResult snapshots in 4.0
source, matching single-dollar execution. A synchronous `$tcpdump ...` assignment
waits for completion; three-value unpacking does not provide a running stream.
The enter()/expect()/send()/live-buffer examples below retain their existing
interaction semantics, including the published 3.1.5 API.

For a separate continuous process, prefer the 4.0 managed job API with
streaming output, explicit stop and a finite fallback deadline for unattended
agents. In 4.0 source, use console.start() for a foreground job in the
current shell/sudo/su context; enter() remains the interactive conversation API.
Ctrl-C is a stop request, not proof of remote process termination. See the
[canonical execution and long-program guide]({{ site.baseurl }}/v3a/recommended-api/#unreleased-command-results-and-long-running-programs)
for bounded captures, output conditions, cleanup and termination reporting.

<a id="unreleased-stream-in-the-current-console"></a>

## 4.0: stream in the current console

`console.start(command)` returns CommandJob while keeping the current Bash
shell's cwd, environment and identity. Ordinary completed commands remain
unchanged. A console has one foreground job; other console operations are
rejected until it finishes or stops and verifies recovery. Job operations run
on the creating thread. Console start defaults to a 60-second total deadline;
prefer an explicit finite deadline for unattended agents.

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

Replace INTERFACE and provide native account/capture permission. Use nested
su/sudo APIs for identity changes; direct privilege shells and detached/background
jobs are unsupported. Text chunks are not guaranteed lines. PTY stdout/stderr
can merge. Ctrl-C recovery must verify the original UID/PID; unresolved recovery
fails and disables the console. Pipe consoles support completion but cannot safely
cancel a running program. A confirmed shell recovery does not establish that
detached descendants stopped. See the
[executable canonical example]({{ site.baseurl }}/v3a/recommended-api/#unreleased-foreground-jobs-inside-shell-sudo-and-su).

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

Last Updated: 2026-10-08 23:46:37
