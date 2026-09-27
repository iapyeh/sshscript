---
title: "Exceptions and Return Values"
parent: "Reference"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 4
permalink: /v3a/reference/exceptions-and-return-values/
---

# Exceptions and Return Values

> **Next-release API:** This page describes the updated source checkout.
> The published 3.1.4 wheel retains the earlier command/config/check behavior.

This contract describes the updated source API and applies in both normal
Python and `python -O`. The next-release changes below supersede the original
3.1.4 command-return and check behavior.

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

`Session.exec_command()` returns an immutable `CommandResult`. Unpack three
values: `stdout, stderr, exitcode = result`. Output is captured text. The result
also has `host`, `duration`, and `command`; `session.last_result` retains it.
Saved results survive subsequent commands and Session closure.

With `check=False` (the default), nonzero status remains data. With `check=True`,
local and remote one-shot commands raise `subprocess.CalledProcessError` after
saving the result. The exception carries text `stdout`/`stderr` and `result`.

```python
from sshscript import Session

with Session() as session:
    stdout, stderr, exitcode = session.exec_command(["false"])
    if exitcode != 0:
        raise RuntimeError(f"command failed: exitcode={exitcode}")
```

Persistent console commands still return two live buffers, with status on
`console.exitcode`; interactive input reports prompt/exit/silence instead.
Transfers return paths without updating command status. `close()` returns a
success bool and records `close_errors`; `close(strict=True)` raises after
attempting cleanup. Do not depend on `assert` for production failure handling.

See [Results and Error Model](../../concepts/results-and-error-model/) for field
semantics and migration from live output to text snapshots.

## Validation guarantees

One-shot commands accept nonempty strings or nonempty lists/tuples of strings.
Argv disallows an empty executable, NUL, and shell mode. Persistent commands
must be one-line strings;
`get_pty` must be None/bool, and internal `for_with` must be bool. Compiled bytes
regexes are rejected by text matching. Appended output must be str. Invalid
inputs are rejected before command execution or affected buffer mutation.
Failed listener removal, duplicate hijack/release, and last-layer removal do
not alter their associated state.

See [Session and Console API Reference](../session-and-console-api/) for
operation signatures and cleanup details.

Last Updated: 2026-09-26 16:11:31
