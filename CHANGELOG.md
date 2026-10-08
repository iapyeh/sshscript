# Changelog

This project records user-visible changes here. Release artifacts and their
provenance are available from the linked GitHub Release and PyPI pages.

## 4.0.1 — 2026-10-08

- Settle the legacy command worker before propagating timeout/transport errors;
  retain the primary error and report incomplete or failed worker cleanup.

- Attempt every local job stream close independently, and reap even after signal
  failure. Preserve the primary exception and attach subsequent cleanup failures
  as exception notes; report cleanup failure after otherwise successful execution.

- Confirm delayed local child exit with a bounded wait after macOS group-signal
  permission errors; preserve genuine signal failures. Close local job streams
  even when forced cancellation fails.

- Test full-duplex binary stdin/stdout/stderr beyond SSH flow-control windows,
  exact EOF, transport loss, missing exit status, and repeated resource cleanup.
  The credential-free SSH fixture forwards stdin to a real subprocess.
- Feed legacy SSH stdin concurrently with output readers to prevent a flow-control
  deadlock when a command writes output before consuming input. Close the owned
  channel and settle I/O workers on failure; missing SSH exit status raises
  EOFError rather than becoming a completed result with exitcode -1.
- Extend native OpenSSH regression coverage to bulk transmission, execution-time
  disconnection, nested SSH and ProxyJump cleanup/host-key rejection. CI and
  release transport jobs test the metadata minimum and Paramiko 3.x/4.x.

- Identify development artifacts as 4.0.0.dev0 rather than the published 3.1.5.
  Target 4.0 for incompatible execution-contract changes; document migration,
  exact-version diagnostics and release channels in VERSIONING.md. Block
  prerelease/local versions in the production publication paths.

- Preserve `input=` unchanged on local, SSH, and managed execution paths; remove
  the legacy SSH-only newline addition. Line-oriented stdin callers must supply
  their own newline. Document explicit console `input()` (one added Enter),
  `send()` (exact text), and command execution; retain context-dependent aliases
  for compatibility. Add byte/Unicode/EOF and PTY/pipe/.spy regressions.

- Add foreground `console.start()` / `$.start()` jobs inside Bash shell, su and
  sudo contexts, preserving cwd/environment/identity and returning CommandJob.
  Keep synchronous commands unchanged. Enforce one job per console channel and
  creator-thread operations, bounded capture and explicit streaming overflow.
  Verify completion/PTY cancellation using fresh UID/PID handshakes; disable
  unresolved consoles. Reject interactive enter() jobs and common raw privilege,
  background and shell-replacement forms. Add release-tracked protocol, SSH,
  native-auth opt-in, dollar-syntax and executable documentation coverage.

- Never send a weaker SIGINT after a cancellation worker has already sent
  SIGKILL; serialize worker/watcher escalation. Preserve confirmed child exit
  when a concurrent final cancellation signal
  reports a permission error; still expose signal failures for live processes.

- After an explicit authentication rejection, wait for the bounded return
  marker before probing the parent shell. Avoid a Ctrl-C race that can cancel
  the parent return marker on Linux; reject reuse if recovery remains unknown.

- Add opt-in native su/sudo/PAM verification on disposable Ubuntu accounts,
  using the candidate wheel on local and real OpenSSH backends. Require
  identity, failure/body exclusion and confirmed recovery or channel rejection;
  save sanitized candidate evidence in CI and release gates. Other native
  platforms and host-specific policies remain unverified.

- Reject Session close/disconnect while the Session or any descendant owns an
  active console context, before any cleanup or state changes. Track consoles
  independently of latest-command results and unwind tracking on entry/exit
  failure. Release unentered console channels on close and reject new work on
  permanently closed Sessions; retain strict cleanup failure reporting.

- Preserve bare escaped dollars in raw commands such as `$echo \$HOME` on
  Python 3.14, whose tokenizer rejects the shell escape before translation.
  Keep ordinary Python syntax diagnostics unchanged. Run the full local
  language.spy fixture in the standard regression suite.

- Unify completed persistent shell/su/sudo commands and single-dollar commands
  on immutable CommandResult snapshots with three-value unpacking. This breaks
  old two-value console unpacking. Console check failures carry `.result`.
  Preserve live console buffers, expect/send/input and enter() input semantics;
  long-running programs can stream until an explicit stop condition.

- Reject Python versions below 3.11 before loading SSHScript features. CLI
  startup reports the detected version and interpreter path without a traceback;
  Python API imports raise a descriptive ImportError.

- Add `enter_timeout=10` to Session and nested-console `su()`/`sudo()`. Entry's
  lock acquisition, authentication, shell readiness, and setup commands share
  one deadline; successful entry does not wait out a fixed error-observation
  interval. Timeout is an unresolved result, never authentication success.
- Confirm authenticated startup with a unique marker, effective UID and shell
  PID, followed by a readiness handshake. Support passwordless entry and send
  a supplied password at most once. Recover the original parent shell on entry
  failure within a separate two-second budget, or mark the channel unusable.
- Preserve BSD su argument placement, capability-detected `--pty`, and the
  existing sudo-to-su route; protect bootstrap expressions from sudo login-shell
  expansion. Bash is resolved through PATH instead of a fixed `/bin/bash` path.
- Make authenticated console contexts single-use and require `{auth_command}`
  or `{auth_command_quoted}` in custom nested `command=` templates. Document
  migration, exceptions, and native-system validation still required before
  release. Add credential-free PTY/pipe and shell-family regression coverage.
- Release console locks and unwind thread-stack entries on entry/exit failure;
  recognize an already-returned target shell to avoid exiting its parent again.

- Add a canonical version-profiled API guide whose examples execute in CI,
  plus shipped PEP 561 declarations and checked public typing examples.

- Add Session set/get and validated check/verbose/log_level properties, child
  snapshots, context-local CLI defaults, and per-command check overrides
  including persistent shell commands. Session log levels are independent.
- Add Session `policy` settings and properties for missing-host-key policies;
  omitted connect policy inherits the setting, explicit values override it,
  and explicit None keeps default host-key rejection. Child settings inherit
  independently of per-connection overrides.

- Add `Session.start()` and managed `CommandJob` lifetimes, streaming stdout,
  bounded capture, user cancellation, and explicit termination status.
- Add opt-in `exec_command(command_timeout=...)` with the same total deadline
  as `start(timeout=...)` on local and SSH backends. Legacy timeout is unchanged.
- Add `JobResult` and `CommandTimeoutError` with partial output and truncation
  metadata. Local cancellation uses SIGINT then SIGKILL on an owned process
  group; remote cancellation never treats channel closure as proof of a kill.
- Document unlimited tcpdump capture, Ctrl-C, bounded stop grace, and migration.

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

[Unreleased]: https://github.com/iapyeh/sshscript/compare/v3.1.4...release
[3.1.4]: https://github.com/iapyeh/sshscript/releases/tag/v3.1.4
