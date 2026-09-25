---
title: "SSHScript v3.1 Release Notes"
parent: "Migration and Releases"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
---

# SSHScript v3.1 Release Notes

SSHScript 3.1.4 was published on 2026-09-24 as the first Production/Stable
release in the supported v3.1 line. Install it from
[PyPI](https://pypi.org/project/sshscript/3.1.4/) or review the corresponding
[GitHub Release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.4).

The release requires Python 3.11 or newer and supports Python 3.11–3.14 on
Linux and macOS.

## Production hardening

- Package runtime assertions were replaced by the stable exception contract
  documented in [Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).
  Validation remains active under `python -O`; user-written `.spy` assertions
  retain ordinary Python semantics.
- Listener removal, hijack/release, and last-layer checks are atomic and do
  not mutate state when validation fails. Positive Session-stack indexing was
  corrected.
- Invalid commands, PTY modes, patterns, output buffers, and descriptor
  combinations are rejected before execution or buffer mutation.
- Closed and hijacked channel operations, AST invariants, persistent commands,
  and disconnected SFTP access now use stable documented exception types.
- Normal, optimized, compile, Dollar-syntax, and package AST assertion gates
  are part of the credential-free release checks.

## Security

- SSH connections verify system host keys by default. Insecure automatic key
  acceptance now requires an explicit Paramiko policy.
- Interactive SSH sessions do not forward the complete local environment;
  only terminal and locale defaults plus explicitly supplied values are sent.
- Remote private keys are read through SFTP instead of interpolated shell
  commands.
- Upload and download INFO logs no longer reveal SSH hostnames or complete
  local and remote paths.
- CodeQL, Dependabot, private vulnerability reporting guidance, and an
  OIDC-based trusted publishing workflow were added.
- Release actions and build tools are pinned. Distributions are hashed and
  attested, and the GitHub Release stays in draft until PyPI publication
  succeeds.

## Fixed

- Remote stdout and stderr are drained concurrently, and stdin EOF is sent.
- Session cleanup failures are observable through `close_errors` and may be
  made strict with `close(strict=True)`.
- `$.break(code)` is preserved as the CLI exit status.
- `run_file()` executes exactly one file. Programs should compose scripts
  through ordinary Python imports instead of directory or glob execution.
- `.spy` importing is explicit through `sshscript.spy_imports()` and is
  scoped automatically while `run_file()` is executing.
- Importing SSHScript no longer patches `threading.Thread`, warning handling,
  or `__main__`.
- `.spy` threads retain Session inheritance through a context-aware Thread
  created by the source transformer, not a process-wide monkey patch.
- `Session()` construction is side-effect free. Session-stack activation is
  scoped to execution, context managers, or an explicit unscoped
  `$.connect()` operation.

See [Contributing and Testing](../development-and-testing/) for the release gate
that validates these behaviors without SSH credentials.

## Packaging and project policy

- Package metadata, the MIT license, security and support policies,
  contributor guidance, and CI configuration are included in the public
  release repository.
- `tools/run_checks.py` provides the canonical credential-free gate.
  `tools/check_release.py` builds the sdist and wheel, validates metadata,
  installs the wheel in a fresh environment, and writes a SHA-256 manifest.
- Public CI tests Python 3.11–3.14 on Linux and macOS. Separate disposable
  OpenSSH jobs cover host keys, SFTP, PTY behavior, `sudo`/`su`, and timeouts.

## Publication and provenance

The tagged 3.1.4 release passed the complete public matrix and release OpenSSH
integration jobs. The release workflow built and attested the distributions,
published them to PyPI through its Trusted Publisher using a short-lived OIDC
credential, and made the GitHub Release public only after PyPI accepted the
artifacts. The release retains `verified.json` with the distribution hashes.

- [Release workflow run](https://github.com/iapyeh/sshscript/actions/runs/35963068790)
- [PyPI release](https://pypi.org/project/sshscript/3.1.4/)
- [GitHub Release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.4)

Provenance establishes the origin and integrity of an artifact; it does not
replace source review or validation against the target organization's SSH,
PAM, `sudoers`, network, and host-key policies.

Last Updated: 2026-09-25 16:37:52
