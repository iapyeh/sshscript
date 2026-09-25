---
title: "CLI and Environment Variables"
parent: "Reference"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
---

# CLI and Environment Variables

SSHScript v3.1 can run a regular Python file or a `.spy` file from the
command line. The CLI deliberately accepts one script file at a time.

## Run one script

After installing the package:

```sh
sshscript automation.spy
```

From a source checkout:

```sh
python3 src/sshscript/sshscript.py automation.spy
```

This form assumes the public `release` checkout's `src/` package layout.
Ordinary users should use the installed `sshscript` command.

The path must name one existing regular file. Directories, globs, iterables,
and multiple file paths are not supported. Compose a larger automation
project with ordinary Python imports; `run_file()` temporarily enables peer
`.spy` imports.

Arguments not consumed by the SSHScript CLI remain available to the script
through `sys.argv`.

## CLI options

| Option | Purpose |
| --- | --- |
| `-s`, `--script` | Show converted Python source without executing it. |
| `-v`, `--verbose` | Stream command stdout and stderr to the console. |
| `--stderr` | Stream stderr only. |
| `-d`, `--debug [LEVEL]` | Enable debug logging; the default debug level is 10. |
| `--traceback` | Show the full exception traceback. |
| `--version` | Print the installed SSHScript version. |
| `--check-updates` | Check the latest compatible stable PyPI release; this requires Internet access. |
| `--check` | Alias for `--check-updates`. |

For ordinary runtime exceptions, the default error record avoids printing
command payloads. Syntax errors are different: even without `--traceback`,
Python can print the filename, line, source text, and caret. Use `--traceback`
only when its diagnostic value outweighs the risk; keep secrets out of source
and review every diagnostic before sharing it.

Normal completion returns status 0. `$.break(code)` becomes the CLI process
status, while `$.exit(code)` exits with the requested status.

## Run from Python

`sshscript.run_file()` applies the same one-file rule:

```python
import sshscript

status = sshscript.run_file("automation.spy")
```

The function accepts a `str` or `os.PathLike` path to one existing regular
file and returns 0 after normal completion or the status supplied to
`$.break(status)`. It creates and closes a local Session, sets `__name__` to
`"__main__"`, supplies `__file__`, and temporarily adds the script directory
to `sys.path`.

Use `sshscript.run_script(source)` when the program already has source text
in memory.

## Import `.spy` modules explicitly

Importing SSHScript does not globally teach Python to load `.spy` files.
Enable the importer only around imports that need it:

```python
import sshscript

with sshscript.spy_imports():
    import automation  # loads automation.spy
```

`spy_imports()` is temporary, reversible, and safe to nest. `run_file()`
enables it only while the selected script runs, so imports between `.spy`
files work without leaving a process-wide importer installed.

## Environment variables

Pass only the values a command needs:

```python
from sshscript import Session

session = Session()
try:
    session.exec_command(
        "python3 -c \"import os; print(os.environ['DEPLOY_ENV'])\"",
        shell=False,
        env={"DEPLOY_ENV": "staging"},
    )
finally:
    session.close(strict=True)
```

Interactive SSH channels do not forward the complete local process
environment. They send terminal and locale defaults (`TERM`, `LC_ALL`, and
`LANG`) plus values explicitly provided by the caller. This prevents an
unrelated local token or secret from being copied to a remote process.

`KEEPALIVE_INTERVAL` controls the SSH transport keepalive interval. Its
default is 60 seconds; set it to 0 to disable keepalives for a process.

## Process-wide behavior

Importing `sshscript` is intentionally quiet and scoped. It does not install
the `.spy` importer, replace `threading.Thread`, change warning formatting,
configure application logging, alter the environment, or replace the asyncio
event-loop policy. CLI-specific logging and warning formatting are enabled
only by the CLI.

See [Contributing and Testing](../development-and-testing/) for the
credential-free release gate and isolated integration-test guidance.

Last Updated: 2026-09-25 16:37:52
