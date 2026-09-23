# SSHScript

[![CI](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml/badge.svg?branch=release)](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml)
[![CodeQL](https://github.com/iapyeh/sshscript/actions/workflows/codeql.yml/badge.svg?branch=release)](https://github.com/iapyeh/sshscript/actions/workflows/codeql.yml)

SSHScript is a Python automation library and `.spy` script runner for executing
commands locally or over SSH. It provides a regular Python `Session` API and a
compact dollar syntax for automation scripts.

## Installation

SSHScript requires Python 3.11 or newer.

Use `sshscript --version` to display the installed version, or
`sshscript --check-updates` to query PyPI for a newer stable release compatible
with the current Python version. The check only prints an upgrade command;
it does not install anything. `--check` remains an alias. A failed query exits
with status 1; a successful check exits with status 0, whether an update exists
or not. This checks release Python requirements, not dependency resolution or
platform availability.

```sh
python3 -m pip install sshscript
```

For a release checkout containing `src/sshscript/`, `python3 -m pip install .`
installs that checkout. The flat development checkout is not an installable
package; use the following checks instead:

```sh
python3 -m pip install 'paramiko>=2.11,<5' 'packaging>=21' build twine
python3 tools/run_checks.py
python3 tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE
```

See [RELEASING.md](RELEASING.md) for synchronization and publishing. SSHScript
3.1 is the supported production line; a GitHub source update does not by itself
publish a new version to PyPI. See the
[v3.1 documentation](https://iapyeh.github.io/sshscript/v3a/).

## Python API

```python
from sshscript import Session

session = Session()
try:
    stdout, stderr = session.exec_command("uname -a", shell=False)
    print(str(stdout))
    print(session.exitcode)
finally:
    session.close(strict=True)
```

Pass command arguments as a safely quoted string, for example with
`shlex.join()`, and use `shell=False` when shell expansion is not required.

## Running `.spy` files

```sh
sshscript automation.spy
```

The CLI and `run_file()` execute exactly one file. Directories, globs, and
multiple paths are intentionally unsupported. Compose larger automation with
SSHScript include syntax or ordinary Python imports.

Importing SSHScript does not globally enable Python imports of `.spy` files.
Use the explicit, temporary importer when a regular Python program needs one:

```python
import sshscript

with sshscript.spy_imports():
    import automation  # loads automation.spy
```

`run_file()` enables this importer only for the duration of the script, so
imports between `.spy` files continue to work without additional setup.
Threads created with `threading.Thread(...)` inside a `.spy` file inherit the
session that is active when the thread is constructed, without patching the
process-wide `threading.Thread` class.

## SSH host-key security

SSH connections verify system host keys by default and reject unknown or
changed keys. Load the server key into `known_hosts` before connecting.

Accepting a new key without verification must be an explicit decision:

```python
import paramiko

remote = session.connect(
    "user@new-host.example",
    policy=paramiko.AutoAddPolicy(),
)
```

Do this only in a trusted bootstrap environment. Interactive SSH sessions do
not forward the complete local process environment; only terminal/locale
defaults and values explicitly supplied through `env={...}` are sent.

## Tests

The canonical credential-free release gate is:

```sh
python3 tools/run_checks.py
```

It includes normal and optimized unit tests, compile checks, the package assert
scan, and the `.spy` language smoke suite. Public CI additionally provisions a
disposable loopback OpenSSH server to validate real SSH, SFTP, host-key, PTY,
sudo/su and timeout behavior against the built wheel.

The `.spy` language smoke suite can also be run directly:

```sh
python3 sshscript.py unittest/dollar_syntax.spy
```

Site-specific and credentialed SSH tests live under `unittest-v3/` and are not
part of the default release gate. See [CONTRIBUTING.md](CONTRIBUTING.md) before
running them.

## Project status

Version 3.1 is production/stable software. Public behavior is covered by the
credential-free release gates and isolated OpenSSH integration CI. Operators
should still validate site-specific PAM, sudoers, network and host-key policy in
a disposable environment before production rollout.

SSHScript is released under the MIT License.
See [SUPPORT.md](SUPPORT.md), [SECURITY.md](SECURITY.md),
[CONTRIBUTING.md](CONTRIBUTING.md), and [CHANGELOG.md](CHANGELOG.md) for project
policies and release history.

## Production exception contract

SSHScript validates runtime inputs in both normal and optimized Python modes.
See [the stable exception matrix](EXCEPTIONS.md). `AssertionError` was never a
supported SSHScript API contract. User-written `.spy` assertions remain ordinary
Python assertions: `python -O` removes them. Production scripts must use explicit
status checks or `check=True` for command-success handling.

```python
with Session() as session:
    session.exec_command("false", check=True)
```

A nonzero exit status otherwise remains result data, available as
`session.exitcode`.
