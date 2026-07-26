---
title: "Module API"
parent: "SSHScript v3 Documents"
nav_order: 1
---

# Module API

SSHScript can also be used as a regular Python module. This is useful when a
project does not use the `.spy` dollar syntax, or when it needs to
integrate SSHScript with an existing Python application.

The public `Session` API executes local commands by default and exposes
the same output, error, and exit-code information used by dollar syntax:

```python
import sshscript

session = sshscript.Session()
try:
    stdout, stderr = session.exec_command(["hostname"])
    print(str(stdout).strip())
    print(session.exitcode)
finally:
    session.close()
```

See [`$`](Basic/dollar) for the equivalent `.spy` syntax.

## Developer self-tests

The source checkout includes a credential-free test suite for the regular
Python module API:

```text
unittest/test_sshscript_module.py
```

It intentionally contains no dollar syntax, does not open an SSH connection,
and does not read a private key, username, or password. Every command uses a
local subprocess, so it is suitable for a developer's first verification
after changing the module implementation.

From the root of the SSHScript source checkout, run:

```sh
python3 -m unittest discover -v -s unittest -p 'test_sshscript_module.py'
```

The suite uses Python's standard `unittest` framework. It verifies:

- creation, initial state, and repeatable cleanup of a local `Session`;
- structured argument lists, standard input, environment variables, standard
  output, standard error, and exit codes;
- automatic shell detection and explicit shell selection with
  `Session.exec_command()`;
- argument validation before a process starts;
- `run_script()` and sorted multi-file `run_file()` execution; and
- independent local sessions running in worker threads.

An assertion failure produces a non-zero exit status and identifies the
behaviour that does not match the checked-out source.

## Run all credential-free developer tests

The module suite can be run together with the dollar syntax suite:

```sh
python3 -m unittest discover -v -s unittest -p 'test_sshscript_*.py'
```

This command is deliberately limited to localhost-only tests. Integration
tests that exercise real SSH hosts, privilege changes, or private keys are
separate and require their own environment configuration.

Last Updated: 2026-07-25 16:59:40
