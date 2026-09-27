---
title: "Migrating to v3.1"
parent: "Migration and Releases"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
permalink: /v3a/migration-and-releases/migrating-to-v3-1/
---

# Migrating to v3.1

> **Next-release API:** This page describes the updated source checkout.
> The published 3.1.4 wheel retains the earlier command/config/check behavior.

This guide updates v3.0 and earlier code to the supported v3.1 contract. Make the
changes in a branch, run credential-free tests first, and validate SSH and
privileged workflows only against isolated test systems.

Before migrating, read [Installation and Verification](../../getting-started/installation-and-verification/).
Version 3.1.4 is the current Production/Stable release on PyPI.

## Migration checklist

- [ ] Use argument lists/tuples for direct commands, or explicit shell strings.
- [ ] Change one-shot unpacking to stdout, stderr, exitcode.
- [ ] Account for automatic SSH config lookup, or set ssh_config=False.
- [ ] Use --check FILE for compile-only validation.
- [ ] Prefer `exec_command()` or `session(...)` over dollar-named Module API
      aliases.
- [ ] Replace `$$` in `.spy` files with the v3.1 single-dollar form.
- [ ] Make every `run_file()` call name exactly one regular file.
- [ ] Replace the removed package-level `run()` helper.
- [ ] Scope imports of `.spy` modules explicitly.
- [ ] Prepare verified SSH host keys before connecting.
- [ ] Pass only the remote environment variables that are required.
- [ ] Make Session ownership and thread failure propagation explicit.
- [ ] Observe cleanup failures and test CLI exit behavior.

## Next-release command contract

The updated source accepts command strings and nonempty lists/tuples of string
arguments. Lists represent one argv, never a batch. They bypass shell detection
and reject shell mode. Earlier 3.1.4 code using shlex.join() remains valid.

```python
result = session.exec_command(["printf", "%s\n", value], check=True)
stdout, stderr, exitcode = result
```

Unpack three values, not two. The result is a CommandResult, not a plain tuple;
indexing, slicing, and tuple(result) expose the same three-value order. Output
is text snapshots rather than live buffers. Buffer-dependent code should use
session.stdout/session.stderr explicitly. The object also retains host,
duration, and command.

Both local and remote one-shot commands accept check=True. CalledProcessError
now contains text output, a normalized string/argv tuple in cmd, and the full
snapshot in result. Earlier local exceptions carried raw subprocess bytes/argv.
Persistent consoles retain their two-buffer/prompt contract.

Local connect() now reads ~/.ssh/config; explicit API arguments win. Use
ssh_config=False to retain configuration-independent connections. A nested
connection skips local config by default. Common Host settings, ProxyCommand,
and ProxyJump are supported; Match, Include, and canonicalization fail clearly.
See [Connections, Authentication, and Bastions]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/Basic/connect/)
for the exact subset and jump-host requirements.

`sshscript --check FILE` compiles without execution. Without a file, `--check`
retains the legacy PyPI update behavior; prefer `--check-updates` for updates.

## Shell behavior and Dollar syntax

With `shell=None`, v3.1 inspects the final command string and selects a shell
when it finds pipelines, redirection, expansion, assignments, builtins, or
other shell syntax. With a local Session, `shell=False` launches the parsed
argument vector without a shell. With a remote Session, SSHScript safely
re-quotes that vector and sends `exec ...` through the SSH server's command
shell, so operators are not interpreted as user shell syntax even though a
server-side shell participates. Use `shell=True` to force a POSIX shell, or
`shell="bash"` for Bash-specific code.

In `.spy` files, one `$` now covers the former direct-command and shell-command
roles:

Before:

```python
$hostname
$$printf 'alpha\\nbeta\\n' | grep beta
```

v3.1:

```python
$hostname
$printf 'alpha\\nbeta\\n' | grep beta
```

The `$$` form remains only as deprecated compatibility behavior. Migrate it
instead of adding new uses.

In Module API code, `Session.onedollar()` and `Session.twodollars()` are
deprecated. Use `exec_command()` or `session(...)` and state the desired
`shell=` behavior. Do not rely on dollar-named aliases exposed by console
wrappers. The old `open()` method is a compatibility alias for `connect()`;
new code should use `connect()`.

## `run_file()` executes one file

v3.1 no longer accepts a directory, glob, list, or multiple paths.

Before:

```python
sshscript.run_file(["prepare.spy", "deploy.spy"])
```

v3.1:

```python
status = sshscript.run_file("deploy_main.spy")
```

Make `deploy_main.spy` compose the program through ordinary Python imports.
`run_file()` temporarily enables imports of peer `.spy` modules and returns
zero on normal completion or the code passed to `$.break(code)`.
`$.exit(code)` and execution exceptions propagate.

The package-level `sshscript.run()` helper has been removed. Use:

```python
namespace = sshscript.run_script(source, varGlobals=initial_values)
status = sshscript.run_file(path, vars=initial_values)
```

`run_script()` accepts source text and returns its namespace. `run_file()`
accepts one path and returns a status.

## `.spy` imports are explicit and scoped

Importing SSHScript no longer installs a process-wide importer. A regular
Python program that imports a `.spy` module must opt in for a bounded block:

```python
import sshscript

with sshscript.spy_imports():
    import automation  # loads automation.spy
```

`run_file()` enables the importer automatically only while the selected
script runs, so imports between `.spy` files continue to work without global
state. Remove code that depends on importing arbitrary `.spy` files after the
scope ends.

## SSH host keys are verified by default

Unknown and changed host keys are rejected unless the caller explicitly
provides another Paramiko policy. Add verified keys to `known_hosts` before a
normal connection.

Before migrating production systems:

1. obtain each server fingerprint through an independent trusted channel;
2. install the verified key for the automation account;
3. test both the expected key and a deliberately wrong key; and
4. remove broad `AutoAddPolicy` workarounds.

An explicit permissive policy belongs only in a controlled bootstrap process
that verifies and persists identity by another trusted mechanism.

## Remote environments are no longer copied wholesale

Interactive SSH sessions no longer forward the complete local process
environment. Pass only the values the remote program needs:

```python
with local.connect("ops@example.net") as remote:
    remote.exec_command(
        "env",
        env={"LC_ALL": "C", "APP_MODE": "maintenance"},
    )
```

The SSH server may reject variables that its configuration does not accept.
Do not put credentials into forwarded environment variables unless the target
protocol and secret-handling policy explicitly require and protect them.

## Session activation and threads are scoped

Creating `Session()` is side-effect free. Importing SSHScript no longer
patches process-wide `threading.Thread`, warning behavior, `__main__`, or
logging.

Ordinary Python worker code should create and close its own Session:

```python
from sshscript import Session


def inspect_host(host):
    local = Session()
    try:
        with local.connect(host) as remote:
            stdout, stderr, exitcode = remote.exec_command(
                "hostname",
                shell=False,
            )
            return str(stdout).strip()
    finally:
        local.close(strict=True)
```

Transformed `.spy` code retains scoped Session inheritance for recognized
Thread constructors, but worker exceptions still need to reach the main
thread. Consume futures or collect and re-raise failures after joining raw
threads.

## Cleanup failures are observable

`close()` now returns a Boolean and stores cleanup problems as
`session.close_errors`. Use strict cleanup when a cleanup failure should fail
the operation:

```python
session = Session()
try:
    session.exec_command("hostname", shell=False)
finally:
    session.close(strict=True)
```

If another exception is already active, retain that primary failure and log
the types and operation names in `close_errors` rather than accidentally
replacing it. See the
[Failure Model and Production Checklist](../../security-and-operations/failure-model-and-production-checklist/).

## Command and transfer result changes

Remote stdout and stderr are drained concurrently and remote stdin receives
EOF after input. Re-test code that depended on timing, partial output, or a
remote program waiting for additional stdin.

Transfers raise exceptions on failure and do not change the latest command's
`stdout`, `stderr`, or `exitcode`. SFTP retains the SSH connection account even
inside `sudo()` or `su()`.

## CLI changes

The canonical update command is:

```sh
sshscript --check-updates
```

`--check` without a file remains an alias; `--check FILE` validates syntax. The command queries stable, non-yanked PyPI
artifacts compatible with the current Python version. It never installs an
update and does not replace verifying the installed version and import path.

Use `--traceback` only for controlled diagnostics:

```sh
sshscript --traceback automation.spy
```

For ordinary runtime exceptions, the default CLI error record avoids command
payloads. Syntax errors are different: even without `--traceback`, Python can
print the filename, line, source text, and caret. A full traceback can expose
additional source, commands, paths, arguments, and secrets, so keep secrets
out of source and review every diagnostic before sharing it.

## Credential-free migration test

Run a local test before any SSH integration:

```python
import shlex
import sys

from sshscript import Session


session = Session()
try:
    command = shlex.join([
        sys.executable,
        "-c",
        "print('v3.1-ready')",
    ])
    stdout, stderr, exitcode = session.exec_command(command, shell=False)
    assert str(stdout).strip() == "v3.1-ready"
    assert str(stderr) == ""
    assert session.exitcode == 0
finally:
    session.close(strict=True)
```

Then run the repository's credential-free gate:

```sh
python3 tools/run_checks.py
```

Run the command from the public repository root. The tool finds the
`src/sshscript` package and runs the normal and optimized unit suites,
Dollar-syntax smoke test, compilation, and package assertion scan from the
correct working directory.

Only after those checks pass should the migration exercise host-key failure,
authentication failure, remote nonzero status, timeout, privilege prompts,
transfers, nested connections, concurrency, and cleanup against an isolated
SSH environment.

## Python and exception compatibility

Use Python 3.11 or newer. Python 3.9 and 3.10 are no longer supported.
Do not catch AssertionError for SSHScript input/state validation: it was never
a supported API contract. Update callers to the explicit exception types in
[Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/). Empty commands and multiline persistent commands raise ValueError;
wrong argument types and compiled bytes regexes raise TypeError. Disconnected
SFTP access raises SSHScriptException in every optimization mode.

## Assertions and production command checks

User-written `assert` statements in `.spy` files retain normal Python semantics.
`python -O` removes them, including calls inside the assertion. They are useful
for illustrative tests, but production scripts must explicitly inspect
`session.exitcode` (or `$.exitcode`) and handle nonzero status, or use
`Session.exec_command(..., check=True)` on local or remote Sessions to raise
`subprocess.CalledProcessError` after preserving the completed result. SSH,
timeout, and transport failures remain exceptions regardless of optimization.

`AssertionError` was never a supported SSHScript API contract. Package runtime
validation now uses explicit exceptions in both normal and optimized modes.
See [Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

Last Updated: 2026-09-26 16:11:31
