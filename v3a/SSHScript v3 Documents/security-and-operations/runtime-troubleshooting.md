---
title: "Runtime Troubleshooting"
parent: "Security and Operations"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 4
permalink: /v3a/security-and-operations/runtime-troubleshooting/
---

# Runtime Troubleshooting

Use this page after the package imports correctly and reports the expected
version. For installation, environment, and shadowed-import problems, start
with
[Installation Troubleshooting]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/troubleshooting-installation/).

## Establish a safe baseline

Before changing SSH, privilege, or prompt settings, prove the local API in the
same interpreter and environment:

```sh
python3 -c "import sshscript; print(sshscript.__version__); print(sshscript.__file__)"
python3 -m pip check
```

Then run a credential-free command:

```python
import shlex
import sys

from sshscript import Session


local = Session()
try:
    command = shlex.join([sys.executable, "-c", "print('ok')"])
    stdout, stderr = local.exec_command(
        command,
        shell=False,
        timeout=10,
    )
    print(repr(str(stdout)), repr(str(stderr)), local.exitcode)
except BaseException as primary:
    if not local.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    local.close(strict=True)
```

Expected result: stdout is `"ok\n"`, stderr is empty, and the exit status is
zero. If this fails, reduce the problem to local command construction before
investigating the network.

## Symptom map

| Symptom | Likely boundary | First checks |
| --- | --- | --- |
| Unknown or changed host key | Server identity | Stop; compare the fingerprint through an independent channel and repair `known_hosts` only after verification. |
| `AuthenticationException` or repeated authentication failure | Client identity or server policy | Confirm username, agent contents, key permissions, allowed methods, certificate lifetime, PAM, and account state. |
| DNS, refused connection, or `NoValidConnectionsError` | Name, route, firewall, port, or listener | Resolve the exact hostname, test the configured port from the runner, and inspect the nested/bastion path. |
| Banner or authentication timeout | Slow, filtered, or non-SSH endpoint | Verify the port and server logs; keep separate connection, banner, and authentication limits. |
| `FileNotFoundError` on a local direct command | Local executable lookup | Check the active environment, `PATH`, and the first argument produced by `shlex.split()`. |
| Exit status 126 or 127 over SSH or shell mode | Permission or command lookup | Inspect sanitized stderr and the non-interactive remote `PATH`; do not assume the login shell profile was loaded. |
| Nonzero status but no Python exception | Command completed unsuccessfully | Inspect `session.exitcode`; nonzero status is result data by default. |
| Wrong arguments or literal `|`, `>`, or `*` | Execution-mode mismatch | Review `shell=` and the final string; use `shlex.join()` plus `shell=False` for arguments, shell mode only for shell syntax. |
| Interactive timeout or EOF | Prompt/protocol mismatch | Capture redacted output, check the prompt regex, PTY choice, locale, application version, and early-exit status. |
| SFTP permission error inside `sudo()` | Identity mismatch | SFTP still uses the SSH connection account; stage the file and move it with a privileged command. |
| Worker printed an error but the job succeeded | Thread result not collected | Consume every `Future.result()` or otherwise propagate worker failure to the coordinator. |
| `close()` returned `False` or strict close raised | Resource cleanup | Inspect the sanitized operation names in `close_errors`; preserve any primary exception. |

## Host key and authentication failures

Do not combine these into one "SSH failed" fallback. They require different
responses:

- Unknown host: provision the independently verified key.
- Changed host key: stop and investigate rotation, DNS/routing error, or attack.
- Bad username or credential: correct the client identity; do not weaken host
  verification.
- Server policy rejection: inspect server-side authentication logs, account
  state, key options, PAM, and certificate constraints.
- Network failure: verify hostname, port, address family, firewall, bastion,
  proxy command, and timeouts.

When agent authentication behaves differently under a service account, inspect
that account's agent socket and key list rather than copying a private key into
the script. For password testing, use `getpass()` in a controlled terminal and
never include the value in diagnostics.

## Command and shell problems

Print or log a sanitized argument vector during development, not the full
command if it may contain secrets. Verify the exact final string and state the
execution mode explicitly:

```python
arguments = ["tool", "--target", user_value]
command = shlex.join(arguments)
stdout, stderr = remote.exec_command(command, shell=False, timeout=20)
```

Local `shell=False` uses direct process execution. Remote `shell=False` safely
re-quotes the arguments and sends `exec ...` through the server's command
shell. A command available in an interactive login shell may be absent from a
non-interactive SSH `PATH`; use a reviewed absolute path or configure an
explicit safe environment.

Automatic detection is quote-aware, but debugging is easier when security-
sensitive code says `shell=False`, `shell=True`, or `shell="bash"`. If a
pipeline works locally and fails remotely, compare shell implementation,
utility versions, locale, working directory, environment, and quoting.

The next command replaces `session.stdout`, `session.stderr`, and
`session.exitcode`. Save `str(stdout)` and `str(stderr)` before issuing another
command when the earlier result is needed.

## Interactive and PTY problems

A prompt that appears visually identical may contain carriage returns, color
codes, terminal control sequences, a hostname, or localized text. During a
controlled test, capture a redacted `repr()` of the relevant output and match
the narrowest stable expression.

A PTY can:

- merge stderr into stdout;
- change buffering and line endings;
- make a program emit terminal control sequences; and
- change whether `sudo`, `su`, or another program accepts input.

Use the PTY mode required by the actual protocol and test both success and
failure. Distinguish `TimeoutError` (the expected state did not arrive),
`EOFError` (the channel ended while waiting), `BrokenPipeError` (an operation
was attempted after closure), and `RuntimeError` (an invalid lifecycle state,
such as using a hijacked channel incorrectly).

## Transfer problems

For `upload()` and `download()`:

1. confirm that the Session is still connected;
2. distinguish local and remote paths;
3. check the SSH account's SFTP permissions, not its `sudo` permissions;
4. verify parent-directory behavior and `overwrite=` policy; and
5. inspect disk space, quotas, mount options, and server SFTP logs.

Transfers raise exceptions and do not update `exitcode`. A disconnected SFTP
request raises `SSHScriptException`; create a new verified connection rather
than trying to reuse a failed transport.

## Threads and lifecycle

In ordinary Python, create and close a Session inside each worker. Do not share
a mutable Session or console concurrently. With an executor, iterate over every
future and call `result()` so the main job cannot report success while a worker
failed.

For transformed `.spy` files, recognized `threading.Thread` constructors carry
the active Session context into the worker. The program must still join the
thread, communicate failures, and close resources.

Leaving the last `with remote:` context closes a remote Session. Leaving a
local Session context only deactivates it; close the root explicitly. If
`close(strict=True)` raises, cleanup has already attempted all known steps.
Read `close_errors` for sanitized operation names and exception types.

## Runtime validation under optimized Python

For argument failures, distinguish `TypeError` (wrong type) from `ValueError`
(invalid content). For channel failures, distinguish `RuntimeError` (invalid
lifecycle transition), `BrokenPipeError` (closed operation), `EOFError` (ended
while waiting), and `TimeoutError`. A disconnected SFTP request raises
`SSHScriptException`; reconnect before accessing SFTP. Do not catch
`AssertionError` as a package validation contract. These checks remain active
under `python -O`. See [Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

## Collect a safe diagnostic bundle

Record enough context to reproduce the boundary without exposing the payload:

- SSHScript, Python, Paramiko, and operating-system versions;
- whether execution is local, direct SSH, nested, or proxy based;
- a sanitized host identifier and port;
- the operation category and explicit `shell=`/PTY choice;
- exit status or exception type, duration, and retry count;
- cleanup outcome; and
- a minimal reproducer with credentials, commands, private paths, and customer
  data removed.

Use `--traceback` only in a controlled environment. Review source lines,
commands, exception text, and paths before sharing. If the problem remains,
consult the [Session and Console API Reference](../../reference/session-and-console-api/)
and open a report using the project's
[support policy](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md).

Last Updated: 2026-09-25 16:37:52
