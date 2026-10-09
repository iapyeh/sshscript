---
title: "Module API or Dollar Syntax?"
parent: "Getting Started"
grand_parent: "SSHScript Documentation"
nav_order: 4
permalink: /v3a/getting-started/module-api-or-dollar-syntax/
---

# Module API or Dollar Syntax?

> **Version scope:** The argv/CommandResult/check/config API is available in 3.1.5.
> Session settings and managed jobs/deadlines are features available in 4.0.2.
> Use the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/) to choose
> examples for your installed version.

SSHScript provides two interfaces to the same Session execution model:

1. the regular Python Module API; and
2. optional Dollar syntax in `.spy` files.

For new production code, begin with the Module API. Add Dollar syntax only
where command-shaped notation makes a small operator-facing entry point
clearer.

## Decision table

| Situation | Start with | Why |
| --- | --- | --- |
| Python application, service, or library | Module API | Ordinary imports, tooling, types, tests, and explicit dependencies. |
| Reusable automation package | Module API | Functions can receive a Session and be unit-tested normally. |
| CI/CD entry point with substantial policy logic | Module API | Security and error decisions remain visible Python code. |
| Short command-oriented procedure | Dollar syntax can help | `$command` keeps the operational sequence compact. |
| Interactive `enter()` workflow | Either | Choose Dollar only if the shorthand improves the whole script. |
| Existing `.spy` estate | Mixed project | Keep a thin `.spy` entry point and migrate reusable logic to `.py` modules. |

## Recommended default: Module API

Use the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/) for the
version-labelled, CI-executed examples. The explanation below targets 3.1.5.

```python
from sshscript import Session


session = Session()
try:
    stdout, stderr, exitcode = session.exec_command(
        ["python3", "--version"],
        check=True,
    )
    if session.exitcode != 0:
        raise RuntimeError(
            f"version check failed with exit status {session.exitcode}"
        )
    print(str(stdout).strip())
except BaseException as primary:
    if not session.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    session.close(strict=True)
```

The Module API is the better default when code must be imported, packaged,
checked by standard Python tooling, embedded in another program, or tested with
ordinary mocks and fixtures.

`exec_command()` and `session(...)` accept a nonempty command string or
a list/tuple of string arguments for one command. Sequences bypass shell
detection. Both return CommandResult, unpacked as stdout, stderr, exitcode.

## Optional Dollar syntax

The same operation can be a compact `.spy` entry point:

```python
$python3 --version

if $.exitcode != 0:
    raise RuntimeError(
        f"version check failed with exit status {$.exitcode}"
    )

print($.stdout.strip())
```

Run it with:

```sh
sshscript version.spy
```

Dollar syntax is transformed by SSHScript. It is not accepted by the normal
Python parser and should not be placed in a `.py` module.

## The core contract is shared

Both interfaces use the same Session, command, result, connection, console,
transfer, and cleanup implementation:

- a command is one non-empty string or argv list/tuple;
- the latest result is `session.stdout`/`stderr`/`exitcode` or
  `$.stdout`/`stderr`/`exitcode`;
- common shell constructs are detected when `shell=None`;
- `shell=False` requests argument-preserving execution;
- `shell=True` or `shell="bash"` requests a shell;
- a nonzero command exit status must be handled explicitly; and
- programming, SSH, transport, timeout, and cleanup failures remain exceptions.

Equivalent expression forms are:

```python
stdout, stderr, exitcode = session.exec_command(command, shell=False)
```

```python
stdout, stderr, exitcode = $(command, shell=False)
```

## One `$` includes shell capability

SSHScript v3.1 does not require `$$` for pipelines, redirection, substitution,
or other recognized shell constructs:

```python
$printf 'alpha\nbeta\n' | grep beta
$VALUE=ready; printf '%s\n' "$VALUE"
$printf report > /dev/null
```

The old `$$` form remains as deprecated compatibility behavior and forces shell
mode. Do not add it to new code. Automatic detection is a bounded heuristic;
state an explicit shell for uncommon grammar:

```python
$("set -o pipefail; producer | consumer", shell="bash")
```

## Recommended mixed-project structure

Use ordinary `.py` modules for policy, configuration, parsing, and reusable
functions. Keep an optional `.spy` entry point thin:

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

Do not maintain two independent implementations of one workflow merely to
offer both syntaxes. Choose one entry point and share ordinary Python functions
underneath it. Peer `.spy` modules can be imported while SSHScript's scoped
import context is active, but reusable code should normally remain conventional
Python.

## Choose now

- If you are unsure, follow the
  [Module API Tutorial]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/tutorial/).
- If you already understand Session lifetimes and want the optional notation,
  follow the [Dollar Syntax Tutorial](../../tutorials/dollar-syntax/).
- For a mixed command-line project, use
  [CLI and Script Composition](../../how-to-guides/cli-and-script-composition/).

Last Updated: 2026-10-09 10:40:03
