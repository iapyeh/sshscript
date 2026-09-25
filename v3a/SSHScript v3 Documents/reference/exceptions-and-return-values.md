---
title: "Exceptions and Return Values"
parent: "Reference"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 4
permalink: /v3a/reference/exceptions-and-return-values/
---

# Exceptions and Return Values

This contract describes the supported v3.1 Production/Stable implementation,
verified with 3.1.4, and applies in both normal Python and `python -O`.

## Exception matrix

| Failure | Exception |
| --- | --- |
| Wrong argument type | `TypeError` |
| Invalid value, content, or combination | `ValueError` |
| Invalid Session/console/channel lifecycle state | `RuntimeError` |
| Operation on a closed channel/transport | `BrokenPipeError` |
| Channel ends while waiting | `EOFError` |
| Timeout | `TimeoutError` |
| Disconnected SFTP access or transfer | `SSHScriptException` |
| Filesystem failure | Appropriate `OSError` subclass |
| SSH/authentication/host-key failure | Original Paramiko exception and traceback |
| Internal AST/data-structure invariant | Descriptive `RuntimeError` |
| Session-stack index outside its bounds | `IndexError`, following deque |

`AssertionError` was never a supported SSHScript API contract. Do not catch it
as input validation. User-written `.spy` assertions remain ordinary Python
assertions and are removed by `python -O`.

## Results and failure handling

`Session.exec_command()` returns `(stdout, stderr)` live output buffers;
`Session.exitcode` records the command status. Nonzero status normally remains
data. Local `check=True` requests `subprocess.CalledProcessError`; remote
callers should explicitly inspect exitcode. Transfers return paths and do not
update command exitcode. `close()` returns a success bool and records
`close_errors`; `close(strict=True)` raises after attempting cleanup.

Production scripts must explicitly check results rather than depend on assert:

```python
from sshscript import Session

with Session() as session:
    stdout, stderr = session.exec_command("false")
    if session.exitcode != 0:
        raise RuntimeError(f"command failed: exitcode={session.exitcode}")
```

## Validation guarantees

Commands must be nonempty strings, persistent commands must be one line,
`get_pty` must be None/bool, and internal `for_with` must be bool. Compiled bytes
regexes are rejected by text matching. Appended output must be str. Invalid
inputs are rejected before command execution or affected buffer mutation.
Failed listener removal, duplicate hijack/release, and last-layer removal do
not alter their associated state.

See [Session and Console API Reference](../session-and-console-api/) for
operation signatures and cleanup details.

Last Updated: 2026-09-24 15:36:45
