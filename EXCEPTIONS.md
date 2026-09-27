# Stable exception contract

The following contract applies with and without `python -O`.

| Failure | Exception |
| --- | --- |
| Wrong argument type | `TypeError` |
| Correct type but invalid value, content, or combination | `ValueError` |
| Invalid session, console, or channel lifecycle state | `RuntimeError` |
| Operation on a closed channel or transport | `BrokenPipeError` |
| Channel ends while waiting | `EOFError` |
| Timeout | `TimeoutError` |
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
