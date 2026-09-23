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

Nonzero command exit status remains data unless `check=True` requests failure
handling. `AssertionError` was never a supported SSHScript API contract.

User-written `assert` in `.spy` files is preserved as Python syntax. Python's
optimized mode removes these statements, including any calls inside them.
Production scripts must not depend on `assert` for command-success handling.
For local execution, use `session.exec_command(command, check=True)`, or explicitly inspect
`session.exitcode` and raise an application exception when appropriate.

`for_with` must be strictly bool. `get_pty` must be None or bool. Commands must
be nonempty strings, and persistent commands must contain only one line.
Compiled bytes regular expressions are not accepted by text-output matching.
Listener removal requires the identical top listener; failed removal, duplicate
hijack/release, and last-layer removal leave their associated state unchanged.

Run release gates from the project root using a supported interpreter:

```sh
python -m unittest discover -v -s unittest -p 'test_*.py'
python -O -m unittest discover -v -s unittest -p 'test_*.py'
python sshscript.py unittest/dollar_syntax.spy
python -m compileall -q -x 'unittest-v3' .
python unittest/check_package_asserts.py
```

CI runs on Python 3.11–3.14 on Linux and macOS. The AST gate scans the flat
package's root Python modules; tests and historical `unittest-v3` are excluded.
