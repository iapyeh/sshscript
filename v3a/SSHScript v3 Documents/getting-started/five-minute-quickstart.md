---
title: "5-Minute Quickstart"
parent: "Getting Started"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
permalink: /v3a/getting-started/quickstart/
---

# 5-Minute Quickstart

> **Version scope:** The argv/CommandResult/check/config API is available in 3.1.5.
> Session settings and managed jobs/deadlines are features available in 4.0.1.
> Use the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/) to choose
> examples for your installed version.

This quickstart proves the v3.1 Module API on localhost. It requires no SSH
server, account, key, password, or network connection.

## Before you begin

Complete [Installation and Verification](../installation-and-verification/).
The one-shot examples here target 3.1.5. Start with the executable examples in
the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/); 4.0
settings and managed-job examples are explicitly separated there.

## Create a script

Save the following as `quickstart.py`:

```python
import sys

from sshscript import Session


session = Session()
try:
    command = [
        sys.executable,
        "-c",
        "print('hello from SSHScript')",
    ]

    stdout, stderr, exitcode = session.exec_command(command, check=True)

    print("stdout:", str(stdout).strip())
    print("stderr:", repr(str(stderr)))
    print("exit code:", session.exitcode)
finally:
    session.close(strict=True)
```

Run it with the same Python environment used for installation:

```sh
python3 quickstart.py
```

Expected output:

```text
stdout: hello from SSHScript
stderr: ''
exit code: 0
```

You have now created a local `Session`, executed one command, captured both
output streams, inspected the process status, and closed every resource.

A local `with Session()` context activates a reusable Session and does not
close it. This script owns the root explicitly. `contextlib.closing(Session())`
is a shorter option that calls `close()` without checking its bool return.
Inspect `close_errors` or use `close(strict=True)` for cleanup reporting, and
preserve an already-raised exception when cleanup also fails. See
[Session Lifecycle](../../concepts/session-lifecycle/).

## What the example establishes

`exec_command()` accepts one nonempty command string or a list/tuple of string
arguments and returns an immutable CommandResult. Unpack exactly three values:
stdout, stderr, exitcode. The Session also updates its latest-result properties.

Inside the existing `try` block, before the Session is closed:

```python
result = session.exec_command(["printf", "%s", "hello"], check=True)
stdout, stderr, exitcode = result
print(result.host, result.duration)
```

Output is captured text. Keep the result to retain output, status, and metadata
after subsequent commands. Argument sequences execute directly, without shell
detection; `shlex.join()` plus `shell=False` remains a valid string-based form.
See [Results and Error Model](../../concepts/results-and-error-model/) for details.

## Use a shell feature deliberately

Add the following before the `finally` block:

```python
    stdout, stderr, exitcode = session.exec_command(
        "printf 'alpha\\nbeta\\n' | grep beta", shell=True, check=True
    )
    print("pipeline:", str(stdout).strip())
```

Expected additional output:

```text
pipeline: beta
```

This example explicitly requests shell execution and checks its exit status. For code
that does not require expansion, redirection, pipelines, or other shell
syntax, prefer an argv list with `check=True`.

## Handle a nonzero command status

A command that starts and exits with a nonzero status does not normally raise
an exception. Pass `check=True` to raise on either backend, or inspect the
returned `exitcode` explicitly:

```python
    failing_command = [
        sys.executable,
        "-c",
        "import sys; sys.exit(7)",
    ]
    stdout, stderr, exitcode = session.exec_command(
        failing_command,
        shell=False,
    )

    if session.exitcode != 0:
        print("command failed with:", session.exitcode)
```

Expected additional output:

```text
command failed with: 7
```

This differs from an API or operational failure. Invalid arguments, a local
`shell=False` startup failure such as a missing executable, local command
timeout, and SSH authentication or transport failures raise exceptions. In
local shell mode or on a remote Session, a missing executable is normally
reported as a nonzero result—commonly exit status `127` with diagnostic
stderr—instead. Handle both exceptions and nonzero command results.

## Next steps

- [Your First SSH Connection](../first-ssh-connection/) securely moves the same
  Session model to an SSH host.
- [Module API Tutorial]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/tutorial/)
  continues through connections,
  privilege contexts, interactive programs, and transfers.
- [Session and Console API Reference](../../reference/session-and-console-api/)
  defines the supported core contract.
- [Failure Model and Production Checklist](../../security-and-operations/failure-model-and-production-checklist/)
  explains how to turn examples into operational code.

Last Updated: 2026-10-08 23:48:09
