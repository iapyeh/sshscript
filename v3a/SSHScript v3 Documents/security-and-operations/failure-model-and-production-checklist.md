---
title: "Failure Model and Production Checklist"
parent: "Security and Operations"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
permalink: /v3a/security-and-operations/failure-model-and-production-checklist/
---

# Failure Model and Production Checklist

SSHScript automation is reliable only when code distinguishes command results,
operational exceptions, and cleanup failures. This page provides that model
and a review checklist for production use.

## The three failure channels

| Channel | What happened | How to detect it |
| --- | --- | --- |
| Command result | The process started and exited, possibly unsuccessfully. | Inspect `session.exitcode`, `stdout`, and `stderr`. |
| API or operational exception | Validation, startup, timeout, prompt, filesystem, network, SSH, or SFTP failed. | Catch only exceptions the operation can handle; otherwise let them propagate. |
| Cleanup failure | Work finished or failed, but a channel, client, socket, or child Session could not be closed cleanly. | Check `close()` and `close_errors`, or use `close(strict=True)`. |

Do not reduce all three channels to a single Boolean. They have different
recovery and reporting requirements.

## Nonzero exit status is data

By default, a command that returns status 7 is a completed command, not a
Python exception:

```python
stdout, stderr = session.exec_command(command, shell=False)

if session.exitcode != 0:
    raise RuntimeError(
        f"command failed with exit status {session.exitcode}"
    )
```

Include a short operation name, host, and exit status in logs. Avoid logging
the complete command or stderr when either can contain passwords, tokens,
private paths, customer data, or command-line secrets.

Local execution can use `check=True`, which may raise
`subprocess.CalledProcessError`. It is not a portable local/remote policy.
Explicit `exitcode` handling gives both backends the same application-level
decision point.

## Exceptions are operational failures

Examples include:

- `TypeError` or `ValueError` for an invalid command or option;
- `FileNotFoundError` when a local executable or transfer source is missing;
- `subprocess.TimeoutExpired` for a local one-shot timeout;
- `TimeoutError`, `EOFError`, or `BrokenPipeError` during console interaction;
- Paramiko authentication, host-key, channel, and SSH exceptions;
- socket and DNS failures;
- filesystem and SFTP permission or path errors; and
- `SSHScriptException` for SSHScript-specific contract failures.

Catch an exception only where the program can add a useful decision: retry a
known transient operation, select a documented fallback, attach safe context,
or roll back. A blanket `except Exception: pass` converts an observable
failure into silent data loss.

## Timeouts are part of the protocol

Every operation that can wait on an external system needs an intentional
limit:

- connection, banner, and authentication timeouts for SSH;
- a backend-appropriate I/O or command timeout;
- prompt and input timeouts for interactive programs;
- output-silence limits for streaming programs; and
- an overall workflow deadline enforced by the application.

```python
with local.connect(
    "ops@example.net",
    timeout=10,
    banner_timeout=10,
    auth_timeout=10,
) as remote:
    stdout, stderr = remote.exec_command(
        "systemctl is-active nginx",
        timeout=20,  # Paramiko channel I/O timeout, not a total deadline
    )
```

A local one-shot `timeout=` is the `subprocess.run()` wall-clock timeout. A
remote one-shot `timeout=` is Paramiko's channel I/O timeout; a process that
continues producing data can run past it, and a timeout does not prove that
the remote process was terminated. Enforce a total remote workflow deadline
with an external supervisor, then reconcile remote state before retrying.
Interactive timeouts have their own channel semantics. Test the exact paths
you deploy. Do not assume that silence means a process has finished; it only
means no new output was observed during the selected interval.

## Retry only when the operation is safe to repeat

Automatic retries are appropriate for a narrow set of transient failures,
such as a connection attempt that definitively failed before authentication
or command dispatch. They are dangerous after an ambiguous disconnect: the
remote command may have changed state even though its result was never
received.

Before adding a retry:

1. Decide whether the operation is idempotent.
2. Determine whether the previous attempt could have reached the target.
3. Use bounded attempts with backoff and a total deadline.
4. Reconnect with a new, verified Session rather than reusing a broken
   transport.
5. Record a correlation identifier that contains no secret.

Prefer commands that converge on a desired state, transactions, unique job
identifiers, and read-before-write verification over blind repetition.

## Close every lifetime you create

Use context managers for remote and console lifetimes, and close the root
local Session explicitly:

```python
from sshscript import Session


local = Session()
try:
    with local.connect("ops@example.net") as remote:
        with remote.shell() as console:
            console.exec_command("pwd")
finally:
    local.close(strict=True)
```

`close(strict=True)` attempts all cleanup before raising. In code that is
already handling a primary exception, avoid accidentally hiding that original
failure with a cleanup exception. Use non-strict cleanup, record
`close_errors`, and preserve both failure records:

```python
try:
    perform_work(local)
except BaseException:
    if not local.close():
        for operation, error in local.close_errors:
            logger.error(
                "cleanup failed: operation=%s type=%s",
                operation,
                type(error).__name__,
            )
    raise
else:
    local.close(strict=True)
```

Do not log `str(error)` unless the exception type is known not to contain a
secret or command payload.

## SSH trust and credentials

SSHScript loads system host keys and rejects unknown or changed keys by
default. Before deployment:

- verify each server fingerprint through an independent trusted channel;
- install the verified key in the account's `known_hosts`;
- treat a changed key as a security event, not an inconvenience; and
- never use `AutoAddPolicy` as a general production workaround.

Prefer an SSH agent, managed short-lived certificate, or protected key file.
Obtain interactive passwords with `getpass` or a secret manager. Never commit
credentials, interpolate a password into a command, or place it in an
exception or log record.

## Command construction

For dynamic arguments, build a list, quote it with `shlex.join()`, and request
argument-preserving execution:

```python
import shlex

arguments = ["install", "-m", "0644", source, destination]
command = shlex.join(arguments)
stdout, stderr = remote.exec_command(command, shell=False)
```

Use shell mode only when the operation actually requires a pipeline,
redirection, expansion, assignment, or shell builtin. `shlex.join()` protects
argument boundaries; it does not authorize an unsafe executable or validate
the business meaning of user input. Locally, `shell=False` launches the
argument vector without a shell. Remotely, SSHScript safely re-quotes the
arguments and sends `exec ...` through the SSH server's command shell; shell
operators are not interpreted as user shell syntax, but a server-side shell
still participates.

## Interactive programs

Interactive automation is a protocol. Define:

- the prompt or output pattern that proves readiness;
- a finite timeout for every expected state;
- the exact text or signal used to exit;
- the expected outcome when the process exits before the prompt;
- whether a PTY merges stderr into stdout; and
- how passwords are supplied without logging them.

Do not match only a broad word such as `password` if unrelated output can
contain it. Prefer the narrowest stable regex and test unexpected prompts,
wrong passwords, early EOF, timeout, and changed application versions.

## Transfers and privileges

`upload()` and `download()` raise exceptions on failure and do not update
`exitcode`. Check their returned paths after success.

SFTP retains the SSH connection account even inside `sudo()` or `su()`. For a
privileged destination, upload to a directory writable by the connection
account, validate the file, then move or install it through a narrowly scoped
privileged command. Apply the reverse pattern to privileged downloads and
remove temporary copies in a `finally` block.

## Threads and ownership

In ordinary Python, create and close a Session inside each worker. Do not
share a mutable Session or console concurrently unless the specific operation
documents that behavior. Always consume `Future.result()` or otherwise return
worker exceptions to the main thread; a printed background traceback must
fail the overall job.

Transformed `.spy` threads have scoped Session inheritance, but that does not
remove the need to join workers, collect errors, and close resources.

## Logging and diagnostics

Production logs should answer who, where, what category of operation, result,
duration, and correlation identifier without exposing payloads. Record:

- a sanitized host identifier and operation name;
- start and finish timestamps or duration;
- exit status or exception type;
- retry count; and
- cleanup outcome.

For ordinary runtime exceptions, the CLI's default error record is
payload-free; a full traceback can expose source, commands, paths, and
secrets. Syntax errors are different: even without `--traceback`, Python's
diagnostic can print the filename, line, source text, and caret. Keep secrets
out of source and generated command text, use `--traceback` only in a
controlled diagnostic environment, and review all output before sharing it.

## Production review checklist

### Version and deployment

- [ ] The installed version is explicitly verified as `3.1.0`.
- [ ] Python and dependency versions are pinned or otherwise reproducible.
- [ ] The credential-free test gate passes in the deployment artifact.
- [ ] Real SSH behavior is tested against an isolated representative host.

### Trust and secrets

- [ ] Host fingerprints are verified and present in `known_hosts`.
- [ ] No permissive host-key policy is used outside controlled bootstrap.
- [ ] Passwords, keys, tokens, commands, and sensitive stderr are redacted.
- [ ] Each account and privilege rule has the minimum required access.

### Commands and interactive protocols

- [ ] Dynamic arguments use `shlex.join()` and `shell=False` where possible.
- [ ] Every nonzero status is classified and handled.
- [ ] Connection, local-command, prompt, streaming, and workflow limits exist.
- [ ] Remote workflow deadlines use an external supervisor, and ambiguous
      outcomes are reconciled before retry.
- [ ] Interactive prompts, early exits, wrong passwords, and EOF are tested.

### State changes and retries

- [ ] Retried operations are demonstrably idempotent or transaction-protected.
- [ ] Ambiguous remote outcomes require reconciliation before another attempt.
- [ ] Partial uploads, temporary files, and rollback steps are defined.

### Concurrency and cleanup

- [ ] Every worker reports failures to the coordinator.
- [ ] Session ownership is explicit per worker.
- [ ] Remote Sessions and consoles use context managers.
- [ ] Root Sessions are closed and cleanup failures are observable.

Last Updated: 2026-09-18 15:58:44
