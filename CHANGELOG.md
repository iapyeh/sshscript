# Changelog

This project records user-visible changes here. Release artifacts and their
provenance are available from the linked GitHub Release and PyPI pages.

## [3.1.5] - 2026-09-27

### Command API and SSH configuration

- Accept argv lists/tuples for a single command, with local direct execution
  and POSIX quoting over SSH; shell mode remains explicit for strings.
- Return immutable CommandResult snapshots with stdout, stderr, exitcode,
  host, duration, and command. Unpacking/indexing now yields three values:
  stdout, stderr, exitcode. Two-value unpacking must be updated.
  Output values are now strings rather than live buffer objects.
- Apply check=True consistently to local and remote one-shot commands after
  preserving results; CalledProcessError carries text output and result.
- Resolve common ~/.ssh/config settings with explicit API overrides; add
  config opt-out, alternate files, and a connection-free settings preview.
  Support ProxyCommand and ProxyJump (the latter uses local OpenSSH).
- Reject unsupported Match/Include/canonicalization rules; warn about other
  unapplied config settings. ProxyJump requires noninteractive authentication
  and verified jump-host keys. Existing host-key checks remain enabled.

### Script validation

- Add check_file(path) and --check FILE to compile Python/dollar syntax without
  executing user code, imports, or commands. The no-file --check update alias
  remains compatible; --check-updates is the explicit update command.
- Map tokenizer indentation errors to the original source file; retain source
  mapping coverage for nested commands, interpolation, multiline expressions,
  and imported .spy modules. Editor integration is deferred.

### Documentation and community

- Reorganize the README around installation, secure first use, compatibility,
  support, and release provenance.
- Add structured issue forms, a pull request template, and a Code of Conduct.
- Clarify supported environments, security boundaries, and public test paths.

## [3.1.4] - 2026-09-24

First Production/Stable release in the 3.1 line. Published through
[PyPI Trusted Publishing](https://pypi.org/project/sshscript/3.1.4/) with
verified artifacts in the
[GitHub Release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.4).

### Production hardening

- Require Python 3.11 or newer; CI targets 3.11, 3.12, 3.13, and 3.14.
- Replace package runtime assertions with the stable exception contract in
  EXCEPTIONS.md, including validation under `python -O`.
- Make listener removal, hijack/release, and last-layer checks atomic and
  non-mutating on failure; fix positive session-stack indexing.
- Reject invalid command, PTY, pattern, and output arguments before execution
  or buffer mutation. Disconnected SFTP access raises SSHScriptException.
- Move embedded stdio tests into the credential-free suite and add normal,
  optimized, and package AST assertion release gates.
- AssertionError was never a supported API contract. User-written `.spy`
  assertions are preserved, but production command-success handling must use
  explicit checks or `check=True`, because optimized Python removes assertions.
- Validate closed and hijacked channel operations, AST invariants, persistent
  commands, PTY modes, and output buffers with stable exception types.


### Security

- Verify SSH host keys by default; insecure automatic key acceptance now
  requires an explicit Paramiko policy.
- Stop forwarding the complete local environment to interactive SSH sessions.
- Read remote private keys through SFTP instead of interpolated shell commands.
- Remove SSH hostnames and complete local/remote paths from upload/download
  INFO logs.
- Add CodeQL, Dependabot, private vulnerability reporting guidance, and an
  OIDC-based trusted publishing workflow.
- Pin release actions and build tooling, attest distributions, retain their
  hash manifest, and keep the GitHub Release in draft until PyPI succeeds.

### Fixed

- Drain remote stdout and stderr concurrently and send stdin EOF.
- Make session cleanup failures observable and optionally strict.
- Preserve `$.break(code)` as the CLI exit status.
- Simplify `run_file()` to execute exactly one file; compose scripts through
  include syntax or Python imports instead of directory/glob execution.
- Make `.spy` importing explicit with `sshscript.spy_imports()` and scope the
  importer automatically while `run_file()` is executing.
- Stop patching `threading.Thread`, `warnings`, and `__main__` during import.
- Preserve `.spy` thread session inheritance with a context-aware Thread
  created by the source transformer instead of a process-wide monkey patch.
- Make `Session()` construction side-effect free and scope stack activation to
  `run()`, context managers, or an explicit unscoped `$.connect()` operation.

### Project

- Add packaging metadata, license, contributor guidance, and CI configuration.
- Add a disposable loopback OpenSSH integration gate covering host keys, SFTP,
  PTY behavior, sudo/su, and timeout handling.

[Unreleased]: https://github.com/iapyeh/sshscript/compare/v3.1.4...release
[3.1.4]: https://github.com/iapyeh/sshscript/releases/tag/v3.1.4
