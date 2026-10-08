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
and slicing use the same order. Unreleased persistent shell commands use the same three-value result.
Interactive input retains its prompt/exit/silence status; it is not a command result.
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

## Authenticated su/sudo consoles (unreleased)

The same contract applies to Session factories and nested console factories.

| Condition | Exception or behavior |
| --- | --- |
| `enter_timeout` is not numeric, or is bool | `TypeError` |
| `enter_timeout` is zero, negative, NaN, or infinite | `ValueError` |
| Custom `command=` lacks an authentication bootstrap placeholder | `ValueError`, before sending that command |
| A password is requested but none was supplied | `PermissionError` |
| Explicit authentication rejection or a second password request | `PermissionError`; the password is not sent again |
| Command exits before readiness, or shell UID/PID differs from the handshake | `RuntimeError`; this is not necessarily a password error |
| Entry deadline expires | `TimeoutError`; authentication success is unconfirmed |
| An authenticated console context is entered a second time | `RuntimeError`; create a new context |
| Parent-shell recovery cannot be confirmed | Channel is marked failed; later commands propagate its stored failure |
| Channel/transport fails or closes during entry | Original I/O failure or `EOFError` |

`enter_timeout` defaults to 10 seconds and bounds `__enter__`, including lock
acquisition, authentication, readiness, and `initials`. Base-shell creation and
capability probing in the factory are outside this budget. Failed entry has a
separate two-second recovery budget. Context exit uses the same duration as a
separate budget for returning to the parent; channel resource cleanup can take
additional time. It is not a wall-clock limit on the entire `with` block.

Failure is raised before the block body runs unless entry completed. A timeout
does not prove that the supplied password was wrong. Recovery must confirm the
parent's original UID/PID before the channel can be reused; `closed == False`
alone does not imply usability. A direct `shell=False` console has no parent
to restore and its owning context closes the channel after failed entry.
Console unwinding releases its lock and thread-stack entry and preserves an
already-propagating exception if exit or resource cleanup also fails.

See [the API guide](API_GUIDE.md#unreleased-authenticated-susudo-consoles) for
usage, custom-command migration, and platform-specific limitations.

## Session close safeguards (unreleased)

`Session.close()` and `disconnect()` raise `RuntimeError` if this Session or
any descendant has an active shell/su/sudo/enter context, independently of
`strict`. This preflight rejection leaves all Session states and resources
unchanged. Leave those contexts before closing the Session.

Once cleanup starts, the Session is permanently disabled even if cleanup
fails. New commands, connections, consoles, script execution and file/key
operations are rejected. `closed` does not imply successful cleanup: the bool
return and `close_errors` report the outcome; `strict=True` raises after cleanup
for failures. Repeated calls retain that outcome. Child close does not close
the parent; an unentered owned console is released by Session close.

## Console foreground jobs (unreleased)

console.start() returns CommandJob with the current Bash console's state.
An active job prohibits other console operations with immediate RuntimeError;
console/job operations reject use from another thread. start inside enter()
raises RuntimeError. Invalid command forms/options fail before dispatch.
A finite console deadline defaults to 60 seconds. Completion or cancellation
must verify the original UID/PID. Only PTY consoles attempt Ctrl-C; cancelled
pipe jobs and unconfirmed recovery disable the channel and raise with partial
`.result` (termination_status="unknown"). Deadline expiry raises
CommandTimeoutError. Native nonzero exit with check=True raises CalledProcessError.
Results may have merged PTY streams. Confirmed shell recovery does not establish
termination of detached descendants. Nested su/sudo APIs are required for
privilege transitions; background/detached jobs are outside the contract.
