---
title: "SSHScript v3.1 Release Notes"
parent: "Migration and Releases"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
---

# SSHScript v3.1 Release Notes

SSHScript v3.1 remains beta. Version 3.1.1 updates the release source and
build workflow; publishing source does not create a PyPI release.

## Security

- SSH connections verify system host keys by default. Insecure automatic key
  acceptance now requires an explicit Paramiko policy.
- Interactive SSH sessions no longer forward the complete local environment.
- Private keys on a connected parent host are read through SFTP instead of
  being interpolated into a shell command.

## Fixed

- Remote stdout and stderr are drained concurrently, and stdin EOF is sent.
- Session cleanup failures are observable through `close_errors` and may be
  made strict with `close(strict=True)`.
- `$.break(code)` is preserved as the CLI exit status.
- `run_file()` executes exactly one file. Programs should compose scripts
  through include syntax or Python imports instead of directory or glob
  execution.
- `.spy` importing is explicit through `sshscript.spy_imports()` and is
  scoped automatically while `run_file()` is executing.
- Importing SSHScript no longer patches `threading.Thread`, warning handling,
  or `__main__`.
- `.spy` threads retain Session inheritance through a context-aware Thread
  created by the source transformer, not a process-wide monkey patch.
- `Session()` construction is side-effect free. Session-stack activation is
  scoped to execution, context managers, or an explicit unscoped
  `$.connect()` operation.

## Project preparation

- Version 3.1.1 fixes the release `src/sshscript/` package mapping and includes
  the MIT license as `LICENSE.txt`.
- A shared allowlist prepares release sources; verification builds an sdist
  and its wheel and tests installation in a fresh virtual environment.
- CI applies the same checks to development and release layouts. Explicit
  publishing checks artifact hashes and uses credentials supplied externally.
- Version metadata is read from `_version.py`; build and upload tools do not
  modify version numbers.

See [Contributing and Testing](../development-and-testing/) for the release gate
that validates these behaviors without SSH credentials.

## Production hardening

- Minimum Python is now 3.11. CI targets 3.11, 3.12, 3.13, and 3.14;
  local validation has passed on Python 3.11, with other matrix runs pending.
- Package runtime assertions are replaced by explicit exceptions that remain
  active under `python -O`; user-written `.spy` assertions are preserved.
- Listener removal, hijack/release, and last-layer validation are atomic and
  leave state unchanged on failure. Session-stack indexing follows deque.
- Invalid command, PTY, pattern, and output arguments are rejected before
  execution or buffer mutation. Disconnected SFTP raises SSHScriptException.
- The credential-free suite passes 98 tests normally and under `-O`; all nine
  dollar-syntax smoke cases pass. Release gates include an AST assertion scan.

These changes do not constitute a Production/Stable release. Passing the published CI matrix, reproducible SSH integration, and the
remaining production requirements are still required before stable release. See [Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

Last Updated: 2026-09-22 15:50:06
