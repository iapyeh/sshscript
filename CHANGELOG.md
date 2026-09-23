# Changelog

## 3.1.4 - 2026-09-23

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
