---
title: "Contributing and Testing"
parent: "SSHScript v3.1 Documentation"
nav_order: 9
---

# Contributing and Testing

SSHScript v3.1 separates credential-free release checks from manual,
site-specific SSH integration tests. The default gate must work on a clean
developer machine without a network connection, SSH agent, private key,
password, or host inventory.

## Development setup

Use Python 3.11 or newer and install the checkout in editable mode:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

## Required checks

Run all checks from the source directory before proposing a change:

```sh
python3 -m unittest discover -v -s unittest -p 'test_*.py'
python3 sshscript.py unittest/dollar_syntax.spy
python3 -O -m unittest discover -v -s unittest -p 'test_*.py'
python3 -m compileall -q -x 'unittest-v3' .
python3 unittest/check_package_asserts.py
```

The first command is the canonical credential-free release gate. A
regression fix should add a credential-free test whenever the behavior can be
reproduced with a local subprocess, in-memory SSH client, or Paramiko test
double.

## Credential-free Module API tests

`test_sshscript_module.py` verifies the regular Python API, and
`test_spy_thread_session.py` verifies Session inheritance in transformed
`.spy` threads. The tests cover:

- import-time isolation for process hooks, warnings, logging, and threads;
- explicit and reversible imports through `sshscript.spy_imports()`;
- importing and constructing the public `Session` class;
- side-effect-free construction and scoped session-stack activation;
- local Session lifecycle and repeatable cleanup;
- string commands assembled with `shlex.join()`, stdin, environment
  variables, stdout, stderr, and exit codes;
- automatic and explicit shell selection;
- invalid command types and empty commands;
- `run_script()` and single-file `run_file()` behavior;
- independent local Sessions in worker threads; and
- connected Session inheritance in `.spy` threads using in-memory SSH
  clients.

The suite uses Python's standard `unittest` framework plus SSHScript's normal
runtime dependencies. No separate test framework is required.

## Credential-free Dollar syntax tests

`unittest/dollar_syntax.spy` is a localhost-only smoke suite:

```sh
python3 sshscript.py unittest/dollar_syntax.spy
```

It covers bare, string, raw-string, expression, and f-string command forms;
result properties; automatic shell selection; string-only command
validation; function bodies; persistent shell contexts; and imports between
`.spy` files.

A standard-library wrapper runs the same suite in an isolated subprocess
with an empty temporary home directory and SSH-agent variables removed:

```sh
python3 -m unittest discover -v -s unittest \
  -p 'test_sshscript_dollar_syntax.py'
```

Run the historical module and Dollar wrapper subset with:

```sh
python3 -m unittest discover -v -s unittest -p 'test_sshscript_*.py'
```

For the complete release gate, continue to prefer the broader `test_*.py`
pattern.

## Language and integration tests

`unittest/language.spy` exercises extended syntax on localhost by default:

```sh
python3 sshscript.py unittest/language.spy
python3 sshscript.py unittest/language.spy --environment=local
```

Its coverage includes one-Dollar replacements for former `$$` behavior,
quote-aware shell selection, explicit shell overrides, results, functions,
persistent shell contexts, `enter()`, and imports between `.spy` modules.
Temporary filesystem assertions use unique paths and clean up in `finally`
blocks.

The `remote`, `threaded`, and `all` environments are manual, credentialed
integration modes:

```sh
python3 sshscript.py unittest/language.spy --environment=remote
python3 sshscript.py unittest/language.spy --environment=threaded
python3 sshscript.py unittest/language.spy --environment=all
```

Configure hosts and credentials in ignored local files or environment
variables. Public documentation and committed tests must not contain real
usernames, host inventories, key paths, passwords, or captured secrets.

## Credentialed test safety

Scenarios under `unittest-v3/` and older integration scripts may connect to
real hosts, change privileges, transfer files, or run administrative
commands. Before running them:

- use disposable test hosts;
- inspect every command for destructive effects;
- keep credentials and inventories outside version control; and
- verify failures in the main process, including failures raised by worker
  threads.

Credentialed success does not excuse a failing credential-free gate. Both
layers must be healthy before release.

## Compatibility and public APIs

Changes to `Session`, `run_file()`, CLI exit statuses, Dollar syntax,
logging, or SSH security defaults require synchronized implementation,
tests, public documentation, and release notes. Avoid silently accepting
insecure behavior.

## Supported matrix and assertion gate

CI targets Python 3.11, 3.12, 3.13, and 3.14 on Linux and macOS. Python 3.11
has passed the local hardening checks; the remaining matrix runs must pass
before release. The dependency-free AST gate rejects `ast.Assert` in shipped
package modules, excluding tests. Regression tests use unittest assertions so
validation remains meaningful under `-O`. Historical `unittest-v3` material is
not part of the credential-free gate and must not be bulk-added to Git.

Last Updated: 2026-09-21 17:45:03
