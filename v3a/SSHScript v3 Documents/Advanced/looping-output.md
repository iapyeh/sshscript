---
title: "Looping Output"
parent: "Advanced"
nav_order: 4
---

# Looping Output

Long-running programs—such as log followers, monitoring commands, backup
tools, and packet captures—produce output before they exit. SSHScript lets a
script process that output as it arrives instead of waiting for the command to
finish.

Use an interactive [`$.enter`](enter) context for the program, then iterate
over `$.stdout(...)`.

## Stream output

```python
with $.enter("ping -c 4 example.net"):
    for line in $.stdout(10):
        print(line, end="")
```

`$.stdout(10)` returns an iterator. It yields received stdout chunks
(normally lines), and resets its ten-second timer every time new output
arrives. If no new output arrives within ten seconds, it raises
`TimeoutError`.

Use this pattern for a continuous command and choose a practical inactivity
timeout:

```python
with $.enter("tail -F /var/log/syslog", exit=chr(3)):
    for line in $.stdout(30):
        if "ERROR" in line:
            print("alert:", line, end="")
```

The `exit=chr(3)` argument tells SSHScript to send Ctrl-C when the
interactive context ends, which is suitable for commands such as `tail`,
`ping`, and `tcpdump`.

## Stop after a condition

The loop may stop normally with `break`. Leaving the `with` block then
closes the interactive program cleanly.

```python
matches = 0

with $.enter("tail -F /var/log/myapp.log", exit=chr(3)):
    for line in $.stdout(60):
        if "completed" in line:
            matches += 1
        if matches == 10:
            break
```

Always give an intentionally endless command an exit action, or ensure that
the command has its own natural completion condition.

## Choose timeout behaviour

The iterator accepts:

```python
$.stdout(timeout=None, silent=False, shift=True)
```

| Argument | Behaviour |
| --- | --- |
| `timeout` | Maximum seconds to wait after the last received output. `None` waits indefinitely. |
| `silent` | When `False` (default), an inactive command raises `TimeoutError`. When `True`, iteration ends normally. |
| `shift` | When `True` (default), each yielded chunk is removed from the live output buffer. When `False`, the buffer is retained. |

Treat unexpected silence as an error:

```python
try:
    with $.enter("tcpdump -n -i eth0", exit=chr(3)):
        for line in $.stdout(15):
            process_packet(line)
except TimeoutError:
    raise RuntimeError("tcpdump produced no output for 15 seconds")
```

For an expected quiet period, use `silent=True`. The loop ends without an
exception once the timeout expires:

```python
with $.enter("./wait-for-work.sh", exit=chr(3)):
    for line in $.stdout(5, silent=True):
        print(line, end="")

# No output for five seconds: continue normally here.
```

## Preserve the accumulated output

Iteration consumes output by default. If the complete buffer is needed after
processing, pass `shift=False`:

```python
with $.enter("./progressive-report.sh", exit=chr(3)):
    for line in $.stdout(20, shift=False):
        print(line, end="")
        if "DONE" in line:
            break

    report = str($.stdout)
```

Use the default consuming behaviour for unbounded streams so that a long
running process does not retain output that has already been handled.

## Local, remote, and privileged commands

The same iterator works in an SSH connection and in other SSHScript contexts:

```python
with $.connect("ops@example.net"):
    with $.sudo(password):
        with $.enter("journalctl -f -u nginx", exit=chr(3)):
            for line in $.stdout(30):
                if "error" in line.lower():
                    print(line, end="")
```

This lets one monitoring loop follow local, remote, nested, or privileged
processes without changing the output-handling code.
