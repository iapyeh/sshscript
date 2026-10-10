---
title: "Dollar Syntax Tutorial"
parent: "Tutorials"
grand_parent: "SSHScript Documentation"
nav_order: 2
permalink: /v3a/tutorials/dollar-syntax/
---

# Dollar Syntax Tutorial

> **Version scope:** The argv/CommandResult/check/config API is available in 3.1.5.
> Session settings and managed jobs/deadlines are features available in 5.0.0.
> Use the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/) to choose
> examples for your installed version.

Dollar syntax is an optional notation for command-oriented `.spy` files. It is
a concise layer over the Session model, not a separate execution engine. Learn
the Module API first and keep reusable application logic in ordinary Python.

## Create your first `.spy` file

Save this as `hello.spy`:

```python
$printf 'SSHScript is ready\n'

if $.exitcode != 0:
    raise RuntimeError(
        f"command failed with exit status {$.exitcode}"
    )

print($.stdout, end="")
```

Run it:

```sh
sshscript hello.spy
```

Expected output:

```text
SSHScript is ready
```

A `.spy` file can otherwise use ordinary Python imports, functions, classes,
context managers, exceptions, and tests. Running it directly with `python3`
does not work because `$command` is not Python syntax.

## Use the supported command forms

```python
$python3 -c "print('bare-command')"
$'printf string-command'
$r'printf raw-command'

command = "python3 -c \"print('expression-command')\""
$(command, shell=False, timeout=10)

import shlex

name = "world"
$f"printf 'hello %s\n' {shlex.quote(name)}"
```

Outside persistent consoles, the parenthesized form accepts a nonempty string
or a nonempty list/tuple of string arguments plus keyword options. A sequence
is one direct command, not a command batch; shell mode is not accepted with argv.

For dynamic arguments, pass an argv list directly:

```python
import shlex
import sys

arguments = [
    sys.executable,
    "-c",
    "import sys; print(sys.argv[1])",
    "hello; still one argument",
]
$(arguments, check=True, timeout=10)
```

An argv list preserves argument boundaries. It does not decide whether the
requested executable or operation is authorized. The string-based
`shlex.join()` form remains supported, but is not the recommended default.

## Read and retain results

A one-shot Dollar command returns CommandResult and updates the active Session.
Unpack its stdout, stderr, and exitcode:

```python
stdout, stderr, exitcode = $python3 -c "import sys; print('out'); print('err', file=sys.stderr)"

print(str(stdout).strip())
print(str(stderr).strip())
print($.exitcode)
```

`$.stdout`, `$.stderr`, and `$.exitcode` always describe the latest command.
The next command replaces that latest result, so retain returned objects and
convert them with `str()` when a stable snapshot is needed.

A nonzero exit status does not automatically raise:

```python
$python3 -c "import sys; sys.exit(7)"

if $.exitcode != 0:
    raise RuntimeError(
        f"operation failed with exit status {$.exitcode}"
    )
```

Do not use `assert` for production command checks. Python can remove assertions
and their expressions under `python -O`.

## Use one `$` for shell features

SSHScript v3.1 detects common shell constructs with quote awareness:

```python
$printf 'alpha\nbeta\n' | grep beta
$true && printf continued
$false || printf recovered
$VALUE=ready; printf '%s\n' "$VALUE"
$printf report > /dev/null
$printf 'host: %s\n' "$(hostname)"
```

Operators inside single quotes remain literal:

```python
$echo '$HOME'
```

Force argument-preserving execution when operator-looking text is data:

```python
arguments = [
    "python3",
    "-c",
    "import sys; print(sys.argv[1:])",
    "|",
    "not-a-pipeline",
]
$(arguments, check=True)
```

Force a shell when intent or shell choice must be explicit:

```python
$("printf 'POSIX shell\n'", shell=True)
$('[[ -n "$BASH_VERSION" ]] && printf "%s\n" "$BASH_VERSION"', shell="bash")
```

The old `$$` form is deprecated compatibility syntax. One `$` now covers both
direct commands and recognized shell features.

## Switch to a remote Session

A connection context changes the active Dollar Session:

```python
with $.connect(
    "example.net",
    username="ops",
    timeout=10,
    banner_timeout=10,
    auth_timeout=10,
):
    $hostname
    if $.exitcode != 0:
        raise RuntimeError(
            f"hostname failed with exit status {$.exitcode}"
        )
    print($.stdout.strip())
```

When the block exits, the remote child closes and the previous Session becomes
active again. Host-key verification remains enabled by default; enroll a key
only after independently verifying its fingerprint.

## Share state in a persistent shell

One-shot commands do not share working directory or environment. Use a console
when later commands depend on earlier shell state:

```python
with $.shell("bash") as console:
    $cd /tmp
    if console.exitcode != 0:
        raise RuntimeError("cd /tmp failed")

    $pwd
    if console.exitcode != 0:
        raise RuntimeError("pwd failed")
    saved_pwd = str(console.stdout)
    saved_stderr = str(console.stderr)

    $printf 'next command\n'
    if console.exitcode != 0:
        raise RuntimeError("printf failed")

print(saved_pwd.strip())  # The saved text is independent of later output.
```

The whole block owns one shell lifetime. Leaving it performs cleanup; it does
not prove that every command succeeded. A failed command followed by a
successful command can leave the latest exitcode at zero. Check each required
step immediately, and preserve needed output as text before the next command.
Use explicit exceptions, not `assert`, for these checks.

Call the named console when command-specific options are needed:

```python
with $.shell("bash") as console:
    stdout, stderr, exitcode = console("pwd", command_timeout=10)
    status = console.exitcode
    saved_stdout, saved_stderr = str(stdout), str(stderr)
    if status != 0:
        raise RuntimeError(f"pwd failed with exit status {status}")
```

In 4.0 source, completed shell commands return immutable CommandResult
snapshots with three-value unpacking, exactly like single-dollar commands.
Published 3.1.5 console calls still return two buffers. `$.set(check=True)` checks
shell commands; `console(command, check=False)` overrides that policy. Console
`command_timeout` limits that command's wait; it does not make the block a job.
For live output from tcpdump, use managed streaming or enter()/expect()/send(),
with an explicit stop condition and cleanup. Assignment to a completed result
cannot observe a still-running command. See the
[long-program choices]({{ site.baseurl }}/v3a/recommended-api/#unreleased-command-results-and-long-running-programs).

The outermost console context owns the channel. Do not retain `console` for use
after its block. For interactive programs, a prompt means readiness for more
input, not necessarily process completion. See
[Results and Error Model]({{ site.baseurl }}/v3a/concepts/results-and-error-model/)
for the lifetime/completion/success distinction and a checked Python helper.

## Put Dollar commands in functions

```python
def run_checked(command):
    stdout, stderr, exitcode = $(command, shell=False)
    if $.exitcode != 0:
        raise RuntimeError(
            f"command failed with exit status {$.exitcode}"
        )
    return str(stdout).strip()


print(run_checked("python3 --version"))
```

For reusable `.py` modules, accept an explicit Session instead. That makes the
dependency visible and simplifies testing.

## Compose with imports

An entry file imports ordinary Python modules normally. It can also import peer
`.spy` modules while SSHScript's scoped importer is active; `run_file()` and
the CLI establish that scope automatically.

```python
import deployment_checks

deployment_checks.run()
```

Use Python imports as the composition mechanism. Keep policy and reusable logic
in `.py` modules whenever possible.

## Understand transformed threads

In transformed source, recognized `threading.Thread(...)` and imported
`Thread(...)` constructors receive a snapshot of the active Session stack. The
snapshot refers to the same Session objects; it does not clone a connection.
Join every worker before leaving the owning context and propagate worker
failures. For concurrent production work, prefer a separately owned Session
per worker rather than sharing mutable latest-result state.

## Verify against the source test

A source checkout includes a credential-free Dollar smoke suite:

```sh
(cd src/sshscript && python3 sshscript.py unittest/dollar_syntax.spy)
```

It exercises command forms, result state, shell detection, explicit execution,
functions, transformed threads, persistent shells, and `.spy` imports on
localhost.

Use the [Dollar Syntax Reference]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/Basic/dollar/)
for lookup and
[How `.spy` Transformation Works](../../concepts/how-spy-transformation-works/)
when debugging transformed code.

Last Updated: 2026-10-10 19:43:07
