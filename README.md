# SSHScript

[![PyPI](https://img.shields.io/pypi/v/sshscript)](https://pypi.org/project/sshscript/)
[![Python](https://img.shields.io/pypi/pyversions/sshscript)](https://pypi.org/project/sshscript/)
[![CI](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml/badge.svg?branch=release)](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml)
[![CodeQL](https://github.com/iapyeh/sshscript/actions/workflows/codeql.yml/badge.svg?branch=release)](https://github.com/iapyeh/sshscript/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/iapyeh/sshscript/blob/release/LICENSE.txt)

SSHScript is a Python automation library for running commands locally and over
SSH through one `Session` API. It also provides optional dollar syntax for
compact `.spy` automation files.

**Current release:** [3.1.5](https://github.com/iapyeh/sshscript/releases/tag/v3.1.5)
(Production/Stable) · **Python:** 3.11 or newer · **Tested:** Python
3.11–3.14 on Linux and macOS

[Documentation](https://iapyeh.github.io/sshscript/v3a/) ·
[PyPI](https://pypi.org/project/sshscript/) ·
[Changelog](https://github.com/iapyeh/sshscript/blob/release/CHANGELOG.md) ·
[Security](https://github.com/iapyeh/sshscript/security/policy) ·
[Support](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)

## Why SSHScript?

- Use the same interface for local subprocesses and remote SSH commands.
- Traverse nested SSH connections without rebuilding connection logic.
- Keep ordinary Python functions, packages, exceptions, data processing, and
  threading around your automation.
- Scope connections, privilege changes, persistent shells, and interactive
  programs with context managers.
- Read stdout, stderr, and exit status directly after each command.
- Add concise dollar syntax only where command-shaped notation improves a
  script.

## Install

SSHScript requires Python 3.11 or newer. Installing in a virtual environment is
recommended:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install sshscript
sshscript --version
```

For a production deployment that requires repeatable dependency resolution,
pin SSHScript and all transitive dependencies in your application's lock file.
To install this release explicitly:

```sh
python3 -m pip install "sshscript==3.1.5"
```

Use `python3 -m pip install --upgrade sshscript` to upgrade. The optional
`sshscript --check-updates` command queries PyPI and prints an upgrade command;
it never installs an update by itself.

## 60-second local quickstart

```python
import shlex
import sys

from sshscript import Session

command = shlex.join([
    sys.executable,
    "-c",
    "print('sshscript is ready')",
])

with Session() as local:
    stdout, stderr, exitcode = local.exec_command(
        command,
        shell=False,
        check=True,
    )
    print(str(stdout).strip())
    print(f"exit code: {local.exitcode}")
```

Expected output:

```text
sshscript is ready
exit code: 0
```

`exec_command()` accepts one nonempty command string or a nonempty list/tuple
of string arguments. An argument sequence means **one command**, not a batch.
Sequences execute directly on the local host and are quoted for a POSIX login
shell over SSH; shell operators inside them are literal arguments. They accept
only `shell=None` or `shell=False`, without `shell_executable`. Use a string
with `shell=True` when you intentionally need shell operators.

```python
with Session() as local:
    result = local.exec_command(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "a; b"],
        check=True,
        timeout=30,
    )
    print(result.stdout, result.exitcode, result.duration)
    stdout, stderr, exitcode = result  # three-value unpacking
```

Each call returns an immutable `CommandResult` containing text `stdout` and
`stderr`, `exitcode`, `host`, `duration`, and `command`. `host` snapshots
`session.host` (`None` locally); it does not execute `hostname`. `duration` is
elapsed monotonic seconds for command execution and output collection,
including communication and worker cleanup but excluding connection setup.
`command` is the normalized string or an immutable tuple of arguments.
`session.last_result` references the most recently completed command; saved
results remain valid after later commands or session closure. Validation
failures leave it alone; starting a command clears it until completion.

Both local and remote commands accept `check=True` to raise
`subprocess.CalledProcessError` for a nonzero status **after** preserving the
result. The exception has text `stdout`/`stderr`, the normalized `cmd`, and a
`result` attribute. With the default `check=False`, a nonzero status is result
data. Connection errors and timeouts propagate unchanged.

Compatibility: the returned object is no longer a tuple of live output
buffers. Unpack exactly three values: stdout, stderr, exitcode. Indexing and
slicing use that same three-value order; old two-value unpacking must change.
Use `session.stdout`/`session.stderr` for the existing buffer interface.
Persistent shell and interactive console APIs retain their existing buffer
and prompt semantics; this result/check contract applies to one-shot Session
commands, including `$` commands outside persistent consoles.

## First secure SSH connection

SSHScript uses Paramiko and verifies system host keys by default. Before the
first connection, place the server key in the account's standard
`known_hosts` file and verify its fingerprint through an independent trusted
channel. Prefer an SSH agent, managed private key, or secret manager over a
password embedded in source code.

```python
from sshscript import Session

with Session() as local:
    with local.connect(
        "ops@example.net",
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
    ) as remote:
        result = remote.exec_command(
            ["uname", "-s"],
            check=True,
            timeout=30,
        )
        print(result.stdout.strip())
```

Unknown and changed host keys are rejected unless the caller explicitly
supplies a different Paramiko policy. Do not use automatic key acceptance in a
production workflow unless a separate trusted bootstrap process has already
verified the key. See the
[SSHScript v3 documentation](https://iapyeh.github.io/sshscript/v3a/) for
nested connections, timeouts, file transfer, `sudo`, `su`, and interactive
programs.

## Reusing SSH configuration

Connections from a local session read `~/.ssh/config` if it exists. Supported
settings are `Host` patterns, `HostName`, `User`, `Port`, `IdentityFile`,
`ProxyCommand`, and `ProxyJump`. Explicit API arguments override config, then
built-in defaults apply. `port=None` means unspecified; an explicit `port=22`
overrides a configured port. Explicit `pkey`, `pkey_path`, or `key_filename`
overrides configured identity files. Host-key verification remains enabled.

```python
# Inspect effective settings without connecting or starting a proxy process.
settings = Session.resolve_connection("production", port=2222)

with Session() as local:
    with local.connect("production") as remote:
        result = remote(["uname", "-s"], check=True)
```

Pass `ssh_config=False` to disable config lookup, or `ssh_config="/path/config"`
to require a particular file. Nested connections do not read local config
unless an explicit file is supplied; proxy options remain unsupported on
nested sessions. `session.host` and `result.host` use the resolved HostName.
`resolve_connection()` returns effective Paramiko keyword arguments plus
`proxyCommand`, when applicable; it performs no network operations.

Config tokens `%h`, `%n`, `%p`, `%r`, `%u`, `%d`, and `%%` are expanded after
explicit overrides for identity paths and configured proxy commands. Other
tokens fail clearly. Explicit `proxyCommand` strings retain their historical
verbatim behavior. Explicit `proxyCommand=None` disables configured proxies.
You can also supply `proxyJump="user@bastion:2222"` or a comma-separated chain.
When both configured proxy types are active, select one explicitly or remove
the conflict; SSHScript does not implement OpenSSH's first-proxy-wins rule.

`ProxyJump` uses the local `ssh` executable to forward to the target, with
batch authentication and strict host-key checks on jump hosts. It requires
known host keys and noninteractive authentication for those hops. The target
connection remains managed and verified by Paramiko. A custom config file is
also passed to `ssh`; otherwise its user config is used when present.

This is a subset of OpenSSH configuration. `Match`, `Include`, and hostname
canonicalization are rejected before lookup; other unapplied options produce
a warning. In particular, alternate known-hosts files and identity-agent
settings are not imported. Treat config and proxy commands as trusted local
inputs; connecting may execute configured proxy programs.

## Optional dollar syntax

Dollar syntax is not ordinary Python syntax. It is normally stored in `.spy`
files; `run_script(source)` also accepts Dollar syntax from an in-memory string.
Both forms use the same session and transport implementation as the module API:

```python
# health.spy
$hostname
if $.exitcode != 0:
    raise RuntimeError("hostname failed")
print($.stdout.strip())

with $.connect("ops@example.net"):
    $uname -s
    if $.exitcode != 0:
        raise RuntimeError("remote uname failed")
```

Run exactly one file with:

```sh
sshscript health.spy
```

Check one file without executing its Python, imports, or commands:

```sh
sshscript --check health.spy
```

The exit status is 0 for valid syntax, 1 for a syntax/read failure, and 2 for
invalid CLI usage. Syntax diagnostics show the original file, line, source,
and caret. `sshscript.check_file(path)` provides the same compile-only check
and raises source-located `SyntaxError` or filesystem errors. It validates
Python/dollar syntax, not shell commands, imported modules, or remote hosts.
`--script` remains available to inspect generated Python without execution.
For compatibility, **`--check` without a file still checks PyPI for updates**;
use `--check-updates` explicitly for that purpose.

In version 3, a single `$` supports direct commands and shell features such as
pipelines and redirection. The old `$$` form is retained for compatibility but
is deprecated. New applications should start with the regular Python module
API and adopt dollar syntax only when its notation is useful.

The CLI and `run_file()` execute one file. Directories, globs, and multiple
paths are intentionally unsupported. Importing SSHScript does not globally
enable imports of `.spy` modules; use the temporary `sshscript.spy_imports()`
context manager when a regular Python program needs that behavior.

## Security model

SSHScript executes commands and Python code; it is not a sandbox. Treat every
`.spy` file, Python module, command string, remote host, and command output as a
trust boundary. In particular:

- never run unreviewed automation with production credentials;
- avoid shell interpolation of external data;
- keep credentials, private keys, inventories, and captured production output
  out of source control;
- verify host keys independently and retain timeouts around network operations;
- validate site-specific PAM, `sudoers`, shell, and network policy in a
  disposable environment before rollout.

See the [security policy](https://github.com/iapyeh/sshscript/security/policy)
for the complete reporting and security model, and the
[stable exception contract](https://github.com/iapyeh/sshscript/blob/release/EXCEPTIONS.md)
for runtime behavior.

## Release confidence and provenance

The 3.1 release line uses the following public controls:

- CI on Linux and macOS with Python 3.11, 3.12, 3.13, and 3.14;
- normal and optimized-mode tests, syntax smoke tests, compile checks, and a
  runtime-assertion gate;
- disposable loopback OpenSSH integration tests for host keys, SFTP, PTY,
  `sudo`/`su`, and timeout behavior;
- CodeQL and Dependabot;
- PyPI Trusted Publishing with short-lived OIDC credentials;
- GitHub build-provenance attestations and a SHA-256 `verified.json` manifest
  attached to the GitHub Release.

Download distributions from [PyPI](https://pypi.org/project/sshscript/) or the
[GitHub Release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.5), not
from unverified mirrors. These controls establish tested behavior, artifact
integrity, and release provenance; they are not a substitute for reviewing the
automation you run or for validating your production environment.

## Compatibility and support

| Component | Current policy |
| --- | --- |
| SSHScript | Latest 3.1.x receives bug and security fixes |
| Python | 3.11–3.14 are continuously tested |
| Platforms | Current Linux and macOS releases |
| SSH | OpenSSH integration is tested on Ubuntu; other servers are best effort |
| Paramiko | Runtime dependency is `>=2.11,<5`; CI resolves a compatible release |
| Windows | Not currently tested or supported |

See the [support policy](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)
for scope, support channels, and the information needed in a useful bug report.

## Development and verification

A release checkout uses the `src/sshscript/` package layout:

```sh
python3 -m pip install 'paramiko>=2.11,<5' 'packaging>=21' build twine
python3 tools/run_checks.py
python3 tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE
```

The output directory must not already exist. `run_checks.py` locates the test
suite under `src/sshscript/unittest/` automatically. See the
[contributing guide](https://github.com/iapyeh/sshscript/blob/release/CONTRIBUTING.md)
before proposing a change and the
[release guide](https://github.com/iapyeh/sshscript/blob/release/RELEASING.md)
for maintainer-only release steps.

## Project policies

- [Changelog](https://github.com/iapyeh/sshscript/blob/release/CHANGELOG.md)
- [Support policy](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)
- [Security policy](https://github.com/iapyeh/sshscript/security/policy)
- [Stable exception contract](https://github.com/iapyeh/sshscript/blob/release/EXCEPTIONS.md)
- [Contributing guide](https://github.com/iapyeh/sshscript/blob/release/CONTRIBUTING.md)
- [Code of Conduct](https://github.com/iapyeh/sshscript/blob/release/CODE_OF_CONDUCT.md)

## License

SSHScript is released under the
[MIT License](https://github.com/iapyeh/sshscript/blob/release/LICENSE.txt).
