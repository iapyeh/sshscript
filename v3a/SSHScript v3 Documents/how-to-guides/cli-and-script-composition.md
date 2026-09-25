---
title: "CLI and Script Composition"
parent: "How-to Guides"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 9
permalink: /v3a/how-to-guides/cli-and-script-composition/
---

# CLI and Script Composition

The SSHScript CLI and `run_file()` deliberately execute one file at a time.
Compose a larger program with ordinary Python modules and scoped `.spy`
imports. Keep the entry point responsible for input, lifetime, and process
status; keep reusable policy in testable `.py` functions.

## Choose an entry point

Use a normal Python package or `.py` file when the Module API is sufficient:

```sh
python3 -m automation
```

Use a thin `.spy` entry point when Dollar notation materially improves the
operator-facing procedure:

```sh
sshscript deploy.spy
```

The CLI creates a fresh local Session, temporarily adds the script directory to
`sys.path`, enables `.spy` imports for the run, and closes the Session when
execution finishes.

## Pass application arguments

Create `inspect.spy`:

```python
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("--environment", required=True)
args = parser.parse_args()

print(f"environment: {args.environment}")
```

Use `--` to separate application arguments from SSHScript options:

```sh
sshscript inspect.spy -- --environment staging
```

Arguments not consumed by the outer CLI remain available through `sys.argv`.
The separator is especially useful when the application option resembles
`--debug`, `--verbose`, `--script`, or another SSHScript option.

Use `--traceback` cautiously. A traceback, generated source, command, path, or
exception payload can expose sensitive data.

## Recommended project layout

```text
automation/
├── deploy.spy
├── automation_lib/
│   ├── __init__.py
│   ├── checks.py
│   └── config.py
└── tests/
    └── test_checks.py
```

Put command construction and checking in ordinary Python:

```python
# automation_lib/checks.py
import shlex


def run_checked(session, arguments, *, timeout=20):
    command = shlex.join(arguments)
    stdout, stderr = session.exec_command(
        command,
        shell=False,
        timeout=timeout,
    )
    if session.exitcode != 0:
        raise RuntimeError(
            f"{arguments[0]} failed with exit status {session.exitcode}"
        )
    return str(stdout)
```

The thin `deploy.spy` entry point can parse inputs and select the active host:

```python
import argparse
import re

from automation_lib.checks import run_checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()

    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.@-]*",
        args.service,
    ):
        parser.error("service has an unsupported unit name")

    with $.connect(
        args.host,
        username=args.user,
        timeout=args.timeout,
        banner_timeout=args.timeout,
        auth_timeout=args.timeout,
    ):
        output = run_checked(
            $.session,
            ["systemctl", "is-active", args.service],
            timeout=args.timeout,
        )
        print(output.strip())


if __name__ == "__main__":
    main()
```

Run it with:

```sh
sshscript deploy.spy -- \
  --host server.example.net \
  --user ops \
  --service example.service
```

The example relies on a managed agent or normal key discovery and on a
previously verified host key. The application must also authorize the supplied
service name; correct quoting is not an authorization decision.

## Compose a module-first application

The same library function can be used without `.spy`:

```python
from sshscript import Session

from automation_lib.checks import run_checked


def read_hostname(session):
    return run_checked(session, ["hostname"]).strip()


def main():
    local = Session()
    try:
        with local.connect(
            "example.net",
            username="ops",
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        ) as remote:
            print(read_hostname(remote))
    except BaseException as primary:
        if not local.close():
            primary.add_note("SSHScript cleanup also failed")
        raise
    else:
        local.close(strict=True)


if __name__ == "__main__":
    main()
```

Using SSHScript does not require every entry point to be a `.spy` file. This
module-first form is the recommended default.

## Import `.spy` modules explicitly from Python

Importing SSHScript does not install a process-wide `.spy` importer. Bound the
import and make the active Session explicit:

```python
import sshscript
from sshscript import Session


session = Session()
try:
    with session:
        with sshscript.spy_imports():
            import operational_tasks

        operational_tasks.run()
except BaseException as primary:
    if not session.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    session.close(strict=True)
```

`spy_imports()` is temporary, reversible, and safe to nest. Modules are still
cached normally in `sys.modules` after import. A module that executes Dollar
commands during import needs an active Session at that time.

## Embed one file or in-memory source

```python
import sshscript


status = sshscript.run_file("deploy.spy")
namespace = sshscript.run_script(
    "answer = seed + 2",
    {"seed": 40},
)
```

`run_file()` accepts one `str` or path-like object naming an existing regular
file. It does not accept a directory, glob, list, or group of files. It returns
zero on normal completion or the status supplied to `$.break(status)`.

`run_script()` executes source held in memory and returns its namespace. Both
create and close a fresh local Session. If an ordinary execution exception is
already active, cleanup failure is attached to it; after success, cleanup
failure raises `RuntimeError`. A cleanup failure overrides a requested
`$.exit()` or `$.break()` control status so resource failure cannot be
reported as the requested status.

## Define process exit behavior

Normal script completion returns status zero. Use an explicit nonzero status at
the entry-point boundary:

```python
if $.exitcode != 0:
    $.exit(2, "service verification failed")
```

`$.exit(code)` becomes the CLI process status. `$.break(code)` becomes the
return value of `run_file()` and the CLI status. An unhandled ordinary exception
or syntax error normally produces CLI status 1.

A command returning nonzero does not automatically terminate the script.
Inspect the Session status and make the application decision explicitly.

## Test the layers separately

1. Unit-test reusable `.py` functions with ordinary Python tests.
2. Test argument validation and command construction without an SSH server.
3. Run the `.spy` entry point against a disposable representative environment.
4. Verify host-key enrollment and authentication independently.
5. Exercise nonzero results, timeout, unavailable host, partial output, and
   cleanup failure.
6. Keep command payloads, credentials, and sensitive environment values out of
   logs and test artifacts.

See
[CLI and Environment Variables]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/cli-and-environment/)
for the option reference and
[How `.spy` Transformation Works](../../concepts/how-spy-transformation-works/)
for importer and transformation details.

Last Updated: 2026-09-25 16:37:52
