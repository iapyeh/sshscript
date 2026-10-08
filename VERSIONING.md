# Version policy and 4.0 migration

SSHScript aims to let engineers and AI reliably execute, understand, and take
over automation. A version identifies a public execution contract, not a
claim that a command or deployment is safe or successful.

## Current contracts

| Version | Contract and status |
| --- | --- |
| 3.1.5 | Published baseline described in API_GUIDE.md; one-shot Session commands return CommandResult, but persistent console calls return two live buffers. |
| 4.0.1 | Production contract: completed console results, settings, managed jobs and authenticated-console handshakes; incompatible with parts of 3.1.5. |

Version 4.0.1 is the first published 4.0 contract, promoted from the development
line after release validation. The patch component was incremented once for
this publication. Native-system validation limits remain documented.
Use the normal Python Session API as the canonical entry point; optional .spy
syntax follows the same versioned execution contract.

## Numbering and compatibility

Versions follow PEP 440 with major.minor.patch compatibility semantics:

- Major: incompatible public return types/unpacking, input data, exceptions,
  lifecycle/cleanup guarantees, authentication or accepted command templates.
- Minor: additive public features that preserve existing execution contracts.
- Patch: compatible fixes. A security fix may require an incompatible restriction;
  release notes must identify that exception, its impact and migration.
- Development: NEXT.devN; increment N when distributing a changed development
  contract. Do not reuse an artifact version for different distributed inputs.
- Candidates: NEXTaN, NEXTbN or NEXTrcN identify prerelease artifacts. This project's
  current production pipeline accepts only stable versions; prereleases use local
  artifacts/TestPyPI until a separate public prerelease channel is authorized.

Old forms may remain temporarily for migration, but new examples use the
canonical API. Deprecations require an explicit warning and replacement guidance;
removal normally waits for a major release. If security or data correctness
requires an earlier restriction, document it explicitly. Compatibility covers
both Python and .spy entry points. Do not reinterpret a timeout or transport
failure as command success, or channel closure as confirmed remote termination.

Only _version.py owns the package version. Edit it in the designated
working_branch directory on branch working_branch. Imports, CLI, wheel/sdist
metadata and version-labelled examples must agree. Merging does not itself
promote a development build. Never edit src/main directly to bump a version.

## Migrate 3.1.5 automation to the 4.0 contract

### Completed console results

Old persistent-console code `stdout, stderr = shell(command)` must become
`result = shell(command)` or `stdout, stderr, exitcode = shell(command)`.
Output fields are retained text snapshots. Use console.stdout/console.stderr
only when intentionally observing live interactive buffers.

<!-- migration-example -->
```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    with local.shell("bash", get_pty=False) as shell:
        result = shell("printf first", check=True)
        shell("printf second", check=True)
        stdout, stderr, exitcode = result
    print(stdout, exitcode)  # first 0; not the second command's live output
```

### Authentication templates and entry failures

Custom nested su/sudo command templates now require a bootstrap placeholder:
`command="sudo -k -S {auth_command}"`, or
`command="su - alice -c {auth_command_quoted}"` with `username="alice"`.
Do not add quotes around either placeholder. A command without one is rejected
before sending it. Create a fresh context for a deliberate retry.
Use Session.enter() for an arbitrary interactive program; it does not promise
an authenticated su/sudo handshake. Catch entry failures outside the with block.
See [the authenticated-console guide](API_GUIDE.md#unreleased-authenticated-susudo-consoles)
for PermissionError, TimeoutError, failed recovery and native-system limits.

### Input, lifetime and managed results

Command input= is exact data on local/SSH/managed paths; callers relying on the
old SSH-only newline addition must pass their own newline, for example
input="answer\n". Console input() intentionally sends one Enter; send() sends
exact text. Input readiness is not a completed command result.

Use command_timeout for a shared total budget; legacy timeout remains backend
specific and cannot be combined with it. Managed output is bounded; inspect
truncation flags and error.result on CommandTimeoutError. Use start() with an
explicit stop condition/deadline and cleanup for streaming. Stop or channel close
may leave remote termination unknown; reconcile that state separately. Do not
replace interactive calls with synchronous result assignment and expect streaming.

Review Session ownership and close_errors/strict cleanup as part of an upgrade;
a context and a cancellation request are not universal termination guarantees.
Run application regressions and the documented native authentication matrix
before upgrading privileged automation.

## Identify the artifact when handing off automation

Record importlib.metadata.version("sshscript") and sshscript.__version__ with
the interpreter/platform and artifact identity; `sshscript --version` reports the
same package version. Pin the exact tested version in the application's lock
file. For a source checkout, also record its commit and whether it is dirty.
A version alone cannot identify uncommitted edits or prove validation passed.
Consult that artifact's version-labelled API guide before generating examples.
Production gates reject prerelease/local versions before uploading; they never
silently relabel development builds as stable.
