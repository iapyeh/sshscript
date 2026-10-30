# Version policy and major differences

> **Development status: not stable.** SSHScript is under active development.
> APIs, CLI options, configuration and data formats may change incompatibly
> without a deprecation period. Pin the exact version or source revision,
> review changes before upgrading, and validate your automation again.

SSHScript aims to let engineers and AI reliably execute, understand, and take
over automation. A version identifies a public execution contract, not a
claim that a command or deployment is safe or successful.

## Current development policy

SSHScript is still in development. Unless the maintainer explicitly requests
backward compatibility, changes do not need to preserve older APIs, CLI behavior,
configuration or data formats. Do not add compatibility layers, legacy aliases,
or fallback/migration tools solely for old versions. Provide only brief notes on
major differences and any necessary caller changes. Historical version and
migration notes below record earlier contracts; they do not impose compatibility
requirements on current development. Version selection and publication still
require their existing authorization.

## Current contracts

| Version | Contract and status |
| --- | --- |
| 3.1.5 | Published baseline described in API_GUIDE.md; one-shot Session commands return CommandResult, but persistent console calls return two live buffers. |
| 4.0.2 | Previous production contract: completed console results, settings, managed jobs and authenticated-console handshakes; incompatible with parts of 3.1.5. |
| 5.0.0 | Previous published contract: calling-host trust by default, explicit local/chain strategies and strict known_hosts file errors; preserves the 4.0 command execution contract. |
| 6.0.0 | Previous release contract: interactive Python/dollar console, normal script completion with stop(), ScriptResult metadata, and removal of old exit/break APIs and control exceptions. |
| 7.0.1 | Current source contract: the 7.0 execution API with resumable maintainer release/documentation workflows and clarified agent result-status guidance. |
| 7.0.0 | Previous release contract: renamed, keyword-only connection options without aliases; hidden program input, console exit controls, diagnostics and terminal output defaults. Source publication does not publish a GitHub Release/PyPI package. |
| 6.1.0 | Public Console(existing_session), host/agent updates, credential hooks, explicit ownership and cleanup/reuse status; unified CLI and corrected program Ctrl-C readiness. |

Version 4.0.1 introduced the published 4.0 contract after release validation.
Version 4.0.2 is a documentation and link maintenance patch with the same public
execution contract. Native-system validation limits remain documented.
Use the normal Python Session API as the canonical entry point; optional .spy
syntax follows the same versioned execution contract.

## 7.0.1 maintenance update

7.0.1 retains the 7.0 execution API and adds maintainer release/documentation
orchestration, its offline tests and clarified exitcode guidance. Public guides
and executable-example profiles identify 7.0.1; the 7.0.0 changes below remain
historical descriptions of when those execution features were introduced.
Publication remains a separate authorized operation.

## 7.0.0 connection parameter changes

These changes define the 7.0.0 source contract. The previously published 6.1.0
package uses the old names. A source push does not publish a new package.
Old names are rejected immediately; there are no compatibility aliases or
migration tools. Update scripts, connection dictionaries and Session settings.

| Previous name | Current name |
| --- | --- |
| `host` parameter | `hostname` |
| `pkey_path` | `parent_key_filename` |
| `proxyCommand` / `proxyJump` | `proxy_command` / `proxy_jump` |
| `policy` | `missing_host_key_policy` |
| `known_hosts` strategy | `known_hosts_source` |
| `--pkey-path` | `--parent-key-filename` |
| `--known-hosts` | `--known-hosts-source` |

Only hostname may be positional. Replace `connect("user@host", "password")`
with `connect("user@host", password="password")`. Explicit username takes
precedence over the embedded username and is never interpreted as a password.
`key_filename` still reads local Python-host files; `parent_key_filename` reads
an RSA key from the calling Session's host. Supply passphrase to decrypt it;
password is the fallback when passphrase is omitted. Do not combine the latter
with pkey or key_filename. Explicit sock is incompatible with nested/proxy
connections. `known_hosts_path` remains a Session setting and is not renamed.

Use the same new policy/source names in `set()`, `get()` and Session properties.
CLI proxy options are `--proxy-command` and `--proxy-jump`; OpenSSH config files
still use their standard `ProxyCommand` and `ProxyJump` directives.
The historical sections below retain the names used by those releases.

## 7.0.0 console changes

The working checkout adds console-only `$.exit()` alongside `exit` and `exit()`.
For entered programs, `$.exit("command")` supplies the exit sequence on departure;
without an explicit or configured sequence, the program stays open with a reminder.
Script-mode `$.exit()`, `Session.exit()` and wrapper `.exit()` remain unavailable.
Script CLI output now defaults to each stream's TTY status, with mutually exclusive
`--quiet`, `--verbose` and `--stderr` overrides. Scripts that also print captured
output may display it twice on a terminal; use `--quiet` when printing it yourself.
Hidden program replies use `$.input(secret=True)`; recognized password prompts
select hidden input in terminal interaction. These are 7.0.0 source changes; the
following migration table is historical.

## 6.0 console and script completion migration

6.0.0 is an incompatible major version, approved for the new execution contract.
A source push and successful CI do not create a GitHub Release, tag or PyPI upload.
The 6.0.0 package was published separately; this historical section records its
script-completion changes. The current source contract is 7.0.1.

| Previous use | 6.0 replacement |
| --- | --- |
| `$.break(code)` or a script-ending `$.exit(...)` | `$.stop(code=0, message="")` for normal early completion; use Python `sys.exit()` when SystemExit is required. |
| `Session.exit()` or wrapper `.exit()` | Removed. Let lexical `with` scopes clean up in scripts; use console helpers for managed console layers. |
| `SSHScriptBreak` / `SSHScriptExit` exception handling | Removed. Inspect ScriptResult for normal completion; Python SystemExit remains separate. |
| Console preview `$.exit()` | Use bare `exit` or `exit()` to leave one layer. |
| Console preview bare-exit reminder or whole-console `exit()` | Both `exit` and `exit()` now leave one layer; `quit` and `quit()` close all layers. |

`Session.run()` and `run_script()` return dictionary-like ScriptResult objects
with `exitcode`, `stopped` and `message` attributes; names initialized before
`$.stop()` are preserved. `run_file()` returns an integer completion status.
Stop affects the nearest script/import boundary and performs normal `finally`
and context cleanup; cleanup failures remain errors.

The new `sshscript console` accepts Python and dollar syntax in the same retained
process. `$hostname` executes a shell command; `hostname` reads a Python name.
Connections automatically enter persistent Bash shells; console exit helpers
manage layers without changing dollar API meanings. Read [the console guide](CONSOLE.md)
for connection, identity, text-program and control-key behavior. Existing users
must update removed API calls and exception handling before upgrading. The 5.0
host-key contract below remains unchanged.

## 5.0 host-key source migration

SSHScript 5.0.0 defaults `known_hosts` to `"parent"`: nested
connections read the calling Session host's known_hosts through SFTP.
4.0.2 reads localhost's known_hosts for every connection. Existing nested
workflows relying on localhost trust records must opt into
`session.set(known_hosts="local")`, or provision the parent's trust file.
The new default requires a readable, valid trust file, even for a local
Session; an empty file allows the configured missing-key policy to decide.
`"chain"` searches the nearest host first and falls back only when no target
record exists, never after a mismatch or file error. `pkey_path` ownership is
unchanged. See [host-key sources](API_GUIDE.md#host-key-sources-unreleased).
This default and the strict file-error behavior are incompatible with 4.0.2,
so they are introduced in a new major version. Explicit `known_hosts="local"`
preserves the previous source location, while still requiring a readable file.

## 6.1.0 public Console integration

The public `Console` and CLI share one implementation. Compatibility with earlier
6.0 CLI behavior is intentionally not maintained: the internal InteractiveConsole
class, open()/execute() startup API, :help/:quit aliases, mode-specific error text
and silent failed-layer removal are gone. Use Console(session), submit(line), the
Python help/quit helpers and explicit cleanup/reuse status. Session SSH/SFTP and
command contracts keep their existing responsibilities.

The maintainer selected 6.1.0 for this feature release under the current
development policy. It includes the above incompatible console changes, without
compatibility aliases. Read [the integration contract](EMBEDDED_CONSOLE.md).

The maintainer selected **7.0.0** for the new connection contract because old
connection arguments, settings and CLI flags are rejected directly.

## Numbering and compatibility

Versions follow PEP 440. During active development, major/minor labels organize
feature releases and do not promise backward compatibility. The maintainer selects
and explicitly approves the release version; do not invent an automatic major bump
or preserve old behavior solely because the selected release is minor.

- Major: a maintainer-selected major milestone or broad contract redesign.
- Minor: a feature release; may include incompatible changes during development.
- Patch: focused corrections or documentation updates; identify any behavior change.

- Development: NEXT.devN; increment N when distributing a changed development
  contract. Do not reuse an artifact version for different distributed inputs.
- Candidates: NEXTaN, NEXTbN or NEXTrcN identify prerelease artifacts. This project's
  current production pipeline accepts only stable versions; prereleases use local
  artifacts/TestPyPI until a separate public prerelease channel is authorized.

During the current development phase, older forms may be removed without a
compatibility layer, deprecation period or migration implementation unless the
maintainer explicitly requests those. Briefly note major differences for both
Python and .spy callers. The numbering rules describe release labels, not a
requirement to maintain old behavior during development. Do not reinterpret a
timeout or transport failure as command success, or channel closure as confirmed
remote termination.

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

*Last modified: 2026-10-30 00:10:17*
