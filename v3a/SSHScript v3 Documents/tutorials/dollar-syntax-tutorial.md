---
title: "Dollar Syntax Tutorial"
parent: "Tutorials"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
permalink: /v3a/tutorials/dollar-syntax/
---

# Dollar Syntax Tutorial

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

The parenthesized form accepts an expression and keyword options. Its value must
be one non-empty string; a list or tuple raises `TypeError`.

For dynamic arguments, build a list in Python, convert it with `shlex.join()`,
and use direct mode:

```python
import shlex
import sys

arguments = [
    sys.executable,
    "-c",
    "import sys; print(sys.argv[1])",
    "hello; still one argument",
]
$(shlex.join(arguments), shell=False, timeout=10)
```

`shlex.join()` preserves argument boundaries. It does not decide whether the
requested executable or operation is authorized.

## Read and retain results

A Dollar command returns stdout and stderr and updates the active Session:

```python
stdout, stderr = $python3 -c "import sys; print('out'); print('err', file=sys.stderr)"

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
$(shlex.join(arguments), shell=False)
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
    $PERSISTED=inside-context
    $printf '%s:%s\n' "$PWD" "$PERSISTED"

    if console.exitcode != 0:
        raise RuntimeError(
            f"shell command failed with exit status {console.exitcode}"
        )
```

Call the named console when command-specific options are needed:

```python
with $.shell("bash") as console:
    stdout, stderr = console("pwd", command_timeout=10)
```

The outermost console context owns the channel. Do not retain `console` for use
after its block.

## Put Dollar commands in functions

```python
def run_checked(command):
    stdout, stderr = $(command, shell=False)
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

Last Updated: 2026-09-25 16:37:52
