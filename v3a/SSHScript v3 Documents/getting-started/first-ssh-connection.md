---
title: "Your First SSH Connection"
parent: "Getting Started"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
permalink: /v3a/getting-started/first-ssh-connection/
---

# Your First SSH Connection

This guide starts from the verified local installation and runs one
deterministic command through SSH. It uses the regular Python Module API, the
recommended interface for applications, libraries, tests, and long-lived
automation.

## Before you connect

Complete [Installation and Verification](../installation-and-verification/)
and the [5-Minute Quickstart](../quickstart/) first. You also need:

- a reachable SSH server and port;
- an authorized account and authentication method;
- the server's host key in the automation account's `known_hosts`; and
- permission to run the example command.

Obtain the host-key fingerprint through an independent trusted channel before
installing a new key. SSHScript loads system host keys and rejects unknown or
changed keys by default. Do not disable that protection just to make an example
connect.

## Connect and run one command

Save this as `first_ssh.py` and replace the target with your verified host:

```python
from sshscript import Session


local = Session()
try:
    with local.connect(
        "example.net",
        username="ops",
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
    ) as remote:
        stdout, stderr = remote.exec_command(
            "printf 'sshscript-ok\n'",
            shell=False,
            timeout=10,
        )

        if remote.exitcode != 0:
            raise RuntimeError(
                "remote verification failed with "
                f"exit status {remote.exitcode}"
            )

        print(str(stdout), end="")
        print(f"exit code: {remote.exitcode}")
except BaseException as primary:
    if not local.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    local.close(strict=True)
```

Run it with the Python environment used to install SSHScript:

```sh
python3 first_ssh.py
```

Expected output:

```text
sshscript-ok
exit code: 0
```

`connect()` created a child Session for the SSH endpoint. The `with` block
owns that remote lifetime and closes it on exit. The root local Session remains
the application's responsibility. The `except` branch preserves a work
failure while recording cleanup failure; the `else` branch makes cleanup
strict after successful work.

`exec_command()` accepts one non-empty command string. Lists and tuples are not
accepted. The returned stdout and stderr objects are live, string-like buffers;
use `str(stdout)` when a stable string snapshot is required.

## Select an authentication source

When no credential option is supplied, Paramiko can use the SSH agent and the
user's normal key discovery. This is often the simplest choice for a developer
workstation or service account whose agent is managed separately.

Select a key file explicitly when the deployment policy requires it:

```python
from pathlib import Path
from sshscript import Session


local = Session()
try:
    with local.connect(
        "example.net",
        username="ops",
        key_filename=str(Path.home() / ".ssh" / "id_ed25519"),
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
    ) as remote:
        stdout, stderr = remote.exec_command(
            "hostname",
            shell=False,
            timeout=10,
        )
        if remote.exitcode != 0:
            raise RuntimeError(
                f"hostname failed with exit status {remote.exitcode}"
            )
        print(str(stdout).strip())
except BaseException as primary:
    if not local.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    local.close(strict=True)
```

Prefer an SSH agent, protected key, short-lived certificate, or approved
credential provider over a password embedded in source. If an interactive
password is unavoidable, obtain it with `getpass.getpass()` and keep it out of
commands, logs, tracebacks, and committed configuration.

## Distinguish command results from connection failures

After a completed command:

- `stdout` contains standard output;
- `stderr` contains standard error; and
- `remote.exitcode` contains the process exit status.

A nonzero exit status is result data and does not raise by default. Check it
whenever success matters. Connection and transport failures do raise
exceptions. Common Paramiko categories include:

- `AuthenticationException` for rejected authentication;
- `BadHostKeyException` for a changed key;
- `SSHException` for SSH negotiation or trust failure; and
- `NoValidConnectionsError`, socket errors, or timeouts for network failure.

Catch only errors for which the program has a meaningful response. Do not turn
an authentication or host-key failure into a blind retry.

## Direct and shell commands

Use argument-preserving execution for a single program invocation:

```python
stdout, stderr = remote.exec_command("uname -a", shell=False)
```

SSHScript can detect common shell constructs when `shell=None`:

```python
stdout, stderr = remote.exec_command(
    "printf 'alpha\nbeta\n' | grep beta",
)
```

For unusual or shell-specific grammar, state the intent:

```python
stdout, stderr = remote.exec_command(
    "set -o pipefail; generate-report | upload-report",
    shell="bash",
)
```

SSHScript is an execution library, not a sandbox. For dynamic values, assemble
an argument list with `shlex.join()` and use `shell=False`. Review
[Direct Execution vs Shell Execution](../../concepts/direct-execution-vs-shell-execution/)
before accepting external input.

## Diagnose the first failure

| Failure | First action |
| --- | --- |
| Unknown host key | Stop and install only a fingerprint verified through an independent channel. |
| Changed host key | Treat it as a security event until rotation or compromise is resolved. |
| Authentication rejected | Verify username, agent/key selection, account state, and server policy. |
| Refused or timed-out connection | Check DNS, address, port, route, firewall, listener, and each bastion hop. |
| Exit status 126 or 127 | Check executable permissions and the non-interactive remote `PATH`. |
| Nonzero status with no exception | Inspect the command contract and sanitized stderr; the command did run. |

For deeper connection options, nested bastions, and proxy commands, continue
with
[Connections, Authentication, and Bastions]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/Basic/connect/).
Before production use, read
[Host Keys, Credentials, and Command Injection](../../security-and-operations/host-keys-credentials-and-command-injection/).

Last Updated: 2026-09-25 16:37:52
