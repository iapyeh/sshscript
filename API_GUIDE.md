# Recommended SSHScript API

This is the canonical entry point for new code and AI-generated examples.
**Version baseline: 3.1.5**, Python 3.11+. Sections marked **unreleased** require
this development checkout; installing `sshscript==3.1.5` does not provide them.
The checkout still reports 3.1.5 while these additions await a release. Do not
infer development feature availability from that version string alone.

## Recommended choices

| Need | Use |
| --- | --- |
| A command with dynamic arguments | `session.exec_command([program, arg, ...], check=True)` |
| Pipelines or shell expansion | A string with explicit `shell=True` or `shell="bash"`; quote dynamic values |
| Retain output | Save the returned result; read `result.stdout`, `stderr`, `exitcode` |
| Shared shell directory/environment | `session.shell()`; check each required command, save buffer text immediately |
| SSH | `with local.connect(...) as remote:`; retain host-key verification |
| Compact script | One `$` in a `.spy` file; use `$(argv, check=True)` for dynamic arguments |
| Consistent total deadline | **Unreleased:** `exec_command(command_timeout=...)` |
| Long-running program | **Unreleased:** `start(timeout=None)`, `stop()`, `wait()` |
| Session-wide failure/output policy | **Unreleased:** `set(...)`, `get(...)`, or matching properties |

## 3.1.5: one command, one retained result

Install the baseline with `python -m pip install "sshscript==3.1.5"`.
An argv list is one command, not a batch. Shell-looking argument text stays data.

<!-- example: {"id":"argv", "profile":"3.1.5", "stdout":"a; b\n"} -->
```python
from contextlib import closing
import sys
from sshscript import Session

with closing(Session()) as local:
    result = local.exec_command(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "a; b"],
        check=True,
    )
    local.exec_command([sys.executable, "-c", "pass"], check=True)
    print(result.stdout.strip())  # Still the first command's output.
```

`CommandResult` is immutable; unpacking yields exactly stdout, stderr, exitcode.
`check=True` raises `subprocess.CalledProcessError` on nonzero exit, with text
stdout/stderr and `.result`. A timeout or transport error is not an exit status.

<!-- example: {"id":"failure", "profile":"3.1.5", "stdout":"failed: 7\n"} -->
```python
from contextlib import closing
import subprocess
import sys
from sshscript import Session

with closing(Session()) as local:
    try:
        local.exec_command([sys.executable, "-c", "raise SystemExit(7)"], check=True)
    except subprocess.CalledProcessError as error:
        print(f"failed: {error.returncode}")
```

## 3.1.5: SSH and optional dollar syntax

Replace the example host with your configured host and verified known-host key.
CI executes this block with a local SSH protocol fixture in place of the login;
it does not contact example.net. OpenSSH integration tests cover the transport
separately in CI.

<!-- example: {"id":"ssh", "profile":"3.1.5", "fixture":"ssh", "stdout":"ready\n"} -->
```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    with local.connect("ops@example.net", timeout=10,
                       banner_timeout=10, auth_timeout=10) as remote:
        result = remote.exec_command(["printf", "%s", "ready"], check=True)
        print(result.stdout)
```

Save dollar syntax as `.spy`, run with `sshscript file.spy`, and syntax-check
without execution using `sshscript --check file.spy`.

<!-- example: {"id":"dollar", "profile":"3.1.5", "stdout":"ready\n"} -->
```python
result = $(["printf", "%s", "ready"], check=True)
print(result.stdout)
```

## Unreleased: settings and managed jobs

Use this source checkout for the following examples. CLI `-v`, `--stderr`, and
`--debug` override root defaults only for that execution. Child Sessions copy
their parent's settings. `set()` validates before changing anything; `get()`
returns a copy. Explicit command options override Session policy.

<!-- example: {"id":"settings", "profile":"unreleased", "stdout":"True\n1\n"} -->
```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    local.set(check=True, verbose=False, log_level="WARNING")
    print(local.get("check"))
    result = local.exec_command(["false"], check=False, command_timeout=5)
    print(result.exitcode)
```

`command_timeout` is a total command budget on both backends; output does not
reset it. `CommandTimeoutError` includes partial output and termination status.
The legacy `exec_command(timeout=...)` retains different subprocess/Paramiko
semantics; do not combine it with `command_timeout`.

For an indefinite command such as tcpdump, use `start(timeout=None)`. This safe
local example uses a small Python process instead of capturing network traffic:

<!-- example: {"id":"stop", "profile":"unreleased", "stdout":"cancelled confirmed\n"} -->
```python
from contextlib import closing
import sys
from sshscript import Session

with closing(Session()) as local:
    with local.start(
        [sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"],
        timeout=None, stop_timeout=1,
    ) as job:
        try:
            next(job.iter_stdout())
        finally:
            result = job.stop()  # Also use this after catching KeyboardInterrupt.
        print(result.stop_reason, result.termination_status)
```

Local stop sends SIGINT, then escalates if needed. Remote PTY stop attempts
Ctrl-C; non-PTY stop closes the channel. Closure alone never confirms remote
termination. Inspect `termination_status`; `unknown` requires reconciliation.
Managed output retains bounded tails (default 1 MiB per stream), with truncation
flags. `iter_stdout()` yields text chunks and reports queue overflow explicitly.

## Lifetime and failure rules

- A root `with Session()` does not close the Session. These examples use
  `contextlib.closing`; it calls `close()` but does not inspect its bool result.
  For strict cleanup reporting, inspect `close_errors` or use `close(strict=True)`;
  preserve any already-propagating exception when reporting cleanup failure.
- Remote Session, shell, and managed-job contexts own their scoped cleanup.
- A shell block manages one shell lifetime. It does not aggregate every command's
  success. Console calls return two buffers, not CommandResult. Copy needed
  output with `str()` before further commands or consumption. In unreleased
  source, shell calls inherit `check`; interactive prompt input does not.
- A successful final shell status does not prove every pipeline stage succeeded.
- `Session.start()` keeps job results independent of Session latest-command state.

## Compatibility forms: read, do not generate

| Old/alternative form | Recommended new code |
| --- | --- |
| `$$command`, `onedollar()`, `twodollars()` | `$command` or `exec_command()`, with explicit shell mode when needed |
| Two-value unpacking of a Session command | A named result or three-value unpacking (console calls still return two buffers) |
| `assert` for command success | `check=True` or an explicit exception |
| Dynamic command built with `shlex.join()` | Pass argv directly; `shlex.join()` remains supported, not deprecated |
| `--check` without a filename for updates | `--check-updates`; reserve `--check file.spy` for syntax validation |

All six executable blocks above carry explicit version profiles and run in CI.
The same source is mirrored into the website; edit this file, then use
`tools/sync_api_guide.py` to refresh the website copy. Additional protocol and
production details remain in the full documentation.
