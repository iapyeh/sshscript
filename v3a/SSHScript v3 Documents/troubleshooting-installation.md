---
title: "Installation Troubleshooting (EN)"
parent: "SSHScript v3.1 Documentation"
nav_order: 9
---

# Installation Troubleshooting (EN)

SSHScript v3.1 requires Python 3.9 or newer. Use the same Python interpreter
for installation and execution to avoid most environment problems.

## Confirm the interpreter

```sh
python3 --version
python3 -m pip --version
```

If Python is older than 3.9, install a supported version and create a fresh
virtual environment.

## Install in a virtual environment

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install sshscript
```

A virtual environment avoids system-package permissions and makes the Python
and `pip` pair explicit.

## `sshscript: command not found`

First verify that the package is installed for the current interpreter:

```sh
python3 -m pip show sshscript
python3 -m pip install --upgrade sshscript
```

If the package is present but the command is unavailable, activate the
virtual environment or add that Python installation's scripts directory to
`PATH`. Running `python3 -m pip` is safer than assuming `pip` and `python3`
refer to the same installation.

## The wrong version is imported

```sh
sshscript --version
python3 -c "import sshscript; print(sshscript.__version__); print(sshscript.__file__)"
```

An older checkout, a local `sshscript.py` file, or another environment can
shadow the installed package. Run the command outside directories containing
a conflicting module and inspect `sshscript.__file__`.

For development from the intended checkout:

```sh
python3 -m pip install -e .
```

## Dependency or build errors

Upgrade packaging tools, then retry:

```sh
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install --upgrade sshscript
```

If installation still fails, record the Python version, operating system, and
the complete package-manager error. Do not include credentials or private
keys in a public report.

## Host-key errors after installation

An `unknown host key` or `host key changed` error means installation worked
and SSHScript's secure connection policy rejected an unverified server.
Verify the server identity and update `known_hosts`. Do not disable
verification as a general workaround. See
[`Session.connect()`](Basic/connect).

## Minimal diagnostics

```sh
python3 --version
python3 -m pip --version
python3 -m pip show sshscript
sshscript --version
```

Use `--traceback` only in a protected diagnostic environment because a full
trace can expose source, commands, paths, or secrets.

Last Updated: 2026-09-14 18:02:02
