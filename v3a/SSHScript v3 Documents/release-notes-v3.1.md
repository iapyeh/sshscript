---
title: "SSHScript v3.1 Release Notes"
parent: "Migration and Releases"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
---

# SSHScript v3.1 Release Notes

> **Version scope:** The argv/CommandResult/check/config API is available in 3.1.5.
> Session settings and managed jobs/deadlines are features available in 4.0.1.
> Use the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/) to choose
> examples for your installed version.

SSHScript 3.1.4 was published on 2026-09-24 as the first Production/Stable
release in the supported v3.1 line. Install it from
[PyPI](https://pypi.org/project/sshscript/3.1.4/) or review the corresponding
[GitHub Release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.4).

The release requires Python 3.11 or newer and supports Python 3.11–3.14 on
Linux and macOS.

<a id="400dev0--unreleased-development-contract"></a>

## 4.0.1 — 2026-10-08

- Confirm delayed local exit after macOS group-signal permission errors with a
  bounded wait. Preserve genuine signal failures.
- Attempt every local stream close and process reap independently. Preserve
  primary exceptions and attach subsequent cleanup errors as exception notes.


These incompatible changes target 4.0, not a 3.1.5 patch. See
[version policy and migration]({{ site.baseurl }}/v3a/migration-and-releases/version-policy/).

- Legacy SSH calls feed stdin concurrently with stdout/stderr collection,
  preventing flow-control deadlock when a child writes output before reading
  input. Owned command channels and I/O workers are cleaned up on failure.
- Missing SSH exit status raises `EOFError` instead of producing a completed
  result with Paramiko's internal `-1` sentinel. Transport loss preserves
  observed managed-job output and never falls back to local execution.
- Boundary regressions cover bulk binary/Unicode transfer, EOF, missing status,
  disconnection and repeated resource cleanup. Native OpenSSH cases add nested
  SSH and ProxyJump cleanup/host-key rejection. Candidate CI/release jobs select
  the minimum Paramiko 2.11.0 and supported 3.x/4.x dependencies; review actual
  results before claiming platform coverage. See
  [the boundary evidence and limits]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/development-and-testing/#transport-and-resource-boundaries-400dev0-unreleased).
- Completed shell/su/sudo commands return immutable CommandResult snapshots,
  matching single-dollar execution. Migrate two-value unpacking to three values
  or named fields; check failures include `.result`.
- Live console buffers and enter()/input()/send()/expect() retain interaction
  semantics. A result is available after completion; use managed jobs or an
  enter() scope for tcpdump with explicit stopping and cleanup.
- See the [canonical guide]({{ site.baseurl }}/v3a/recommended-api/) for version
  profiles, command selection and long-program best practice.

## 3.1.5 — command API and SSH configuration

These changes are available in the published 3.1.5 package. The 3.1.4 wheel
retains its original behavior.

- One-shot commands accept argv lists/tuples or command strings. Sequences
  preserve argument boundaries and reject shell mode.
- Results are immutable CommandResult objects with stdout, stderr, exitcode,
  host, duration, and command. Unpacking/indexing yields three values:
  stdout, stderr, exitcode. Update callers that previously unpacked two.
- `check=True` works locally and remotely after output/status capture. The
  exception carries text output and the completed `result`.
- Local connections resolve common SSH config settings, ProxyCommand, and
  ProxyJump. Explicit overrides, config opt-out, and a no-connection preview
  are available. Unsupported config rules are diagnosed explicitly.
- `--check FILE` and `check_file(path)` validate Python/dollar syntax without
  execution; tokenizer indentation errors map to the original file.
- Persistent console commands retain their two-buffer/prompt contract.
  Editor integration is deferred.

The following sections record the already published 3.1.4 release.

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

<a id="unreleased-authenticated-susudo-console-entry"></a>

## 4.0: authenticated su/sudo console entry

- `Session.su()`, `Session.sudo()`, and nested consoles accept a configurable
  `enter_timeout=10`, with a shared deadline for authentication, shell readiness,
  and initial commands.
- Entry requires unique success markers and target UID/PID checks. Successful
  authentication returns without a fixed password-verification delay.
- Passwordless entry is supported. Supplied passwords are sent at most once;
  rejection and repeated prompts fail without automatic retries.
- Failed entry verifies parent recovery within a separate two-second budget;
  unconfirmed channels reject later commands. Contexts are single-use.
- su uses the `console_info` capability probe for `--pty`; BSD-compatible
  argument ordering and PATH-based Bash lookup avoid distribution-name guesses.
  Native Linux, FreeBSD, and macOS authentication checks remain required before
  release; simulated protocol tests do not establish every PAM/policy variant.
- Custom nested `command=` templates now require a bootstrap placeholder.

These changes are absent from the published 3.1.5 package. See the
[authenticated console API]({{ site.baseurl }}/v3a/reference/session-and-console-api/#authenticated-susudo-entry-unreleased)
and [migration notes]({{ site.baseurl }}/v3a/migration-and-releases/migrating-to-v3-1/).

Last Updated: 2026-10-08 23:48:09
