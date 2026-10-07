# Stable exception contract

The following contract applies with and without `python -O`.

| Failure | Exception |
| --- | --- |
| Wrong argument type | `TypeError` |
| Correct type but invalid value, content, or combination | `ValueError` |
| Invalid session, console, or channel lifecycle state | `RuntimeError` |
| Operation on a closed channel or transport | `BrokenPipeError` |
| Channel ends while waiting | `EOFError` |
| Legacy timeout | Original backend timeout (`subprocess.TimeoutExpired` locally; Paramiko/socket timeout remotely) |
| Managed command deadline | `CommandTimeoutError` (subclass of `TimeoutError`), with partial `JobResult` |
| Managed stdout iterator overflow | `BufferError` |
| Disconnected `Session.sftp`, upload, or download | `SSHScriptException` |
| Filesystem failure | Appropriate `OSError` subclass |
| Paramiko failure | Original Paramiko exception and traceback |
| Internal AST or data-structure invariant failure | Descriptive `RuntimeError` |
| Stack indexing outside its bounds | `IndexError`, following `deque` |

Nonzero command exit status remains data by default. One-shot local and remote
`Session.exec_command(..., check=True)` raise `subprocess.CalledProcessError`
after saving `session.last_result` and channel output/status. The exception's
`output`/`stdout` and `stderr` are text snapshots on both backends; `cmd` is a
string or argument tuple, and `result` is the complete immutable CommandResult.
CommandResult unpacks as exactly three values: stdout, stderr, exitcode; indexing
and slicing use the same order. Persistent consoles retain two-buffer returns.
This replaces the local backend's former raw subprocess exception (byte
output and generated argv). `AssertionError` was never a supported API contract.

User-written `assert` in `.spy` files is preserved as Python syntax. Python's
optimized mode removes these statements, including any calls inside them.
Production scripts must not depend on `assert` for command-success handling.
For local or remote one-shot execution, use `session.exec_command(command, check=True)`, or
explicitly inspect `session.exitcode` and raise an application exception when
appropriate. Persistent consoles retain their separate command/prompt contract.

`for_with` must be strictly bool. `get_pty` must be None or bool. Commands must
be nonempty strings or nonempty lists/tuples of string arguments. Argument
sequences disallow NUL, an empty executable, and shell mode. Persistent
commands must contain only one line.
Compiled bytes regular expressions are not accepted by text-output matching.
Listener removal requires the identical top listener; failed removal, duplicate
hijack/release, and last-layer removal leave their associated state unchanged.

Run the canonical credential-free gates from the public release repository root
using a supported interpreter:

```sh
python3 tools/run_checks.py
```

The runner locates the package and tests under `src/sshscript/`, then executes
normal and optimized test suites, the dollar-syntax smoke suite, compile checks,
and the package-assertion gate. CI runs these checks on Python 3.11–3.14 on
Linux and macOS. The AST gate scans package runtime modules and excludes tests.

## Managed execution (unreleased)

`Session.start(timeout=...)` and `exec_command(command_timeout=...)` share a
monotonic total command budget. None means unlimited; finite values must be
positive. The legacy exec_command timeout remains backend-specific and cannot
be combined with command_timeout. Timeout always raises, regardless of check.
CommandTimeoutError carries command, host, timeout, elapsed, stdout, stderr,
termination_status and result. Missing exit status is None, not success.
JobResult subclasses CommandResult and adds stop_reason, termination_status,
stdout_truncated and stderr_truncated. Managed output retains bounded tails;
start() owns its result independently from Session.last_result. Deliberate stop
returns a cancellation result, even with check=True; natural failures still
raise CalledProcessError. Remote channel closure alone is not confirmation of
process termination. Unconfirmed active-job termination is reported by
Session.close() as a cleanup error. See the timeout guide for the full contract.
