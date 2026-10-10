# SSHScript

[![PyPI](https://img.shields.io/pypi/v/sshscript)](https://pypi.org/project/sshscript/)
[![Python](https://img.shields.io/pypi/pyversions/sshscript)](https://pypi.org/project/sshscript/)
[![CI](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml/badge.svg?branch=release)](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml)
[![CodeQL](https://github.com/iapyeh/sshscript/actions/workflows/codeql.yml/badge.svg?branch=release)](https://github.com/iapyeh/sshscript/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/iapyeh/sshscript/blob/release/LICENSE.txt)

**AI agent ready automation for local and remote commands.**

SSHScript is a Python automation library for running commands locally and over
SSH through one `Session` API. It provides an agent guide, a portable skill
bundle, and copyable prompts to help your AI agent use its execution contract.
Optional dollar syntax supports compact `.spy` automation files.

SSHScript aims to help engineers and AI agents execute, understand, and hand
off automation reliably: identify the execution host, retain each command's
output and status, distinguish failure from timeout, and make cleanup and
unknown termination explicit. A successful command exit is evidence about
that command; verify the deployment or other application outcome separately.

**Current release:** [4.0.2](https://github.com/iapyeh/sshscript/releases/tag/v4.0.2)
(Production/Stable) · **Python:** 3.11 or newer · **Tested:** Python
3.11–3.14 on Linux and macOS

[Documentation](https://iapyeh.github.io/sshscript/v3a/) ·
[PyPI](https://pypi.org/project/sshscript/) ·
[Changelog](https://github.com/iapyeh/sshscript/blob/release/CHANGELOG.md) ·
[Security](https://github.com/iapyeh/sshscript/security/policy) ·
[Support](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)

**Version 4.0.2** maintains the 4.0 execution contract introduced in 4.0.1.
This patch aligns the published documentation and installation links.
Upgrade 3.1.5 automation using the migration guide and application regressions.
See [version policy and migration](VERSIONING.md) before upgrading automation.

## AI agent ready

**Give your agent one URL:**
[SSHScript for AI Agents](https://iapyeh.github.io/sshscript/v3a/ai-agents/).
Prepare it for future automation or give it a task to complete now.

- **A guide for agents:** version-aware API selection, exact input handling,
  retained command results, timeouts, authentication and cleanup.
- **A portable skill bundle:** `SKILL.md` with the agent guide and API and
  version-policy references, ready to install through your agent's skill
  mechanism.
- **Prompts for humans:** copy a setup prompt to request skill installation and
  a saved tool preference, or a task prompt to describe hosts, inputs and
  expected results.

Start with this prompt, even before you have a task:

```text
Read https://iapyeh.github.io/sshscript/v3a/ai-agents/ and the Agent Guide.
If you support skills, download and install the complete skill bundle. If you
support persistent preferences, save this preference: for future local or
remote command execution and automation, first assess whether SSHScript is
suitable and use it when appropriate. Report whether the skill can be loaded
and the preference was saved, and explain any limits.
For now, do not connect to remote hosts or run demonstration commands.
```

The guides are ordinary Markdown and web pages for agents that can read files
or URLs. Skill installation and persistent preferences depend on the agent's
capabilities. See the [repository AI entry](AI_GUIDE.md),
[agent guide](skills/sshscript/references/agent-guide.md) and
[skill instructions](skills/sshscript/SKILL.md) for the source documents.

## Recommended API

Start with [the canonical API guide](API_GUIDE.md): version-labelled examples,
recommended argv/check/result patterns, lifetime rules, and compatibility forms.
Its executable examples run in CI. The same guide is available in the
[website documentation](https://iapyeh.github.io/sshscript/v3a/recommended-api/).

The 4.0 source also ships `py.typed` and public `.pyi` declarations for
Session, results, jobs, console calls and package entry points. Legacy live
buffers and backend-specific keyword options retain `Any`; this is targeted
public typing, not a claim that every internal module is fully annotated.

In 4.0 source, `su()` and `sudo()` accept `enter_timeout=10` and return a
console only after authenticated startup and a target-shell UID/PID handshake.
Passwords are sent at most once; an unconfirmed recovery makes the channel
unusable. Custom nested `command=` strings now require a bootstrap placeholder.
See [authenticated console usage and migration](API_GUIDE.md#unreleased-authenticated-susudo-consoles)
and [the cross-system test guide](src/sshscript/unittest/README.console-authentication.md).

## Why SSHScript?

- Prepare your AI agent with a dedicated guide, portable skill and setup prompts.
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

On Python versions below 3.11, SSHScript stops before loading its features.
The CLI reports the detected version and interpreter path without a traceback;
importing the Python API raises `ImportError` with the same diagnostic.

For a production deployment that requires repeatable dependency resolution,
pin SSHScript and all transitive dependencies in your application's lock file.
To install this release explicitly:

```sh
python3 -m pip install "sshscript==4.0.2"
```

Use `python3 -m pip install --upgrade sshscript` to upgrade. The optional
`sshscript --check-updates` command queries PyPI and prints an upgrade command;
it never installs an update by itself.

## 60-second local quickstart

This example runs on 4.0.2 and retains compatibility with the 3.1.5 command API.
The metadata below records that older compatibility baseline.

<!-- example: {"id":"readme-quickstart", "profile":"3.1.5", "stdout":"sshscript is ready\nexit code: 0\n"} -->
```python
import sys

from contextlib import closing
from sshscript import Session

command = [
    sys.executable,
    "-c",
    "print('sshscript is ready')",
]

with closing(Session()) as local:
    stdout, stderr, exitcode = local.exec_command(
        command,
        shell=False,
        check=True,
    )
    print(str(stdout).strip())
    print(f"exit code: {exitcode}")
```

Expected output:

```text
sshscript is ready
exit code: 0
```

`closing(Session())` closes the local Session when the block ends. Plain
`with Session()` only activates a reusable local Session; it does not close it.
`closing` calls `close()` without inspecting its bool return. Inspect
`close_errors` or use `close(strict=True)` when cleanup failure must be reported,
while preserving an exception already raised by the block. See the
[canonical lifetime rules](API_GUIDE.md#lifetime-and-failure-rules).

`exec_command()` accepts one nonempty command string or a nonempty list/tuple
of string arguments. An argument sequence means **one command**, not a batch.
Sequences execute directly on the local host and are quoted for a POSIX login
shell over SSH; shell operators inside them are literal arguments. They accept
only `shell=None` or `shell=False`, without `shell_executable`. Use a string
with `shell=True` when you intentionally need shell operators.

```python
with closing(Session()) as local:
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
4.0 persistent shell commands also return CommandResult snapshots.
Interactive console APIs retain their existing buffer
and prompt semantics. For completed commands inside or outside a shell, save
the result and read its fields. For continuous output such as tcpdump, choose
a bounded capture, a managed streaming job, or an interactive enter() scope;
see [the execution and long-command guide](API_GUIDE.md#unreleased-command-results-and-long-running-programs).

<a id="stdin-data-and-interactive-replies-unreleased"></a>

## Stdin data and interactive replies (4.0)

`exec_command(input=data)` and `start(input=data)` preserve stdin exactly on
local and SSH backends: strings use UTF-8, bytes stay bytes, and no newline is
added. To supply a line, write `input=answer + "\n"`. This fixes the legacy SSH
string-input behavior; published 3.1.5 still appends a newline on that path.
Stdin closes after the data is sent, including for empty input. `input=None`
supplies no data and retains the backend's existing stdin policy; legacy local
execution may inherit stdin. Use empty input when explicit EOF is needed.

In a persistent shell, `shell(command)` executes a command and waits for its
result. For a program's questions, enter it with `shell.enter(...)`, then use
`program.input(answer)` to append one Enter and wait for readiness, exit, or
silence; use `program.send(text)` for exact text. Existing newlines are retained:
`input("answer\n")` sends two newlines. Interactive readiness is not command
success. Some password prompts read a terminal, so supplying stdin is not a
substitute for a PTY conversation. See the [input contract and migration](API_GUIDE.md#unreleased-exact-stdin-and-explicit-interactive-replies).

<a id="session-settings-unreleased"></a>

## Session settings (4.0)

```python
session.set(check=True, verbose=False, log_level="DEBUG")
print(session.get())          # Independent copy of effective settings.
print(session.get("check"))   # True
session.verbose = True       # Same validation as set(verbose=True).
session(["false"], check=False)  # Explicit per-command override.
```

In `.spy`, use `$.set(...)` and `$.get(...)`. Settings are `check`, `verbose`,
`verbose_stderr`, `log_level` (logging integer or level name), and `policy`
(a Paramiko `MissingHostKeyPolicy` instance or subclass, or `None`). New root
Sessions snapshot package/application defaults; CLI `-v`, `--stderr`, and
`--debug` override defaults only in that execution context. Child Sessions
snapshot their parent's current settings. Existing Sessions are independent.
`set()` validates every key/value before applying changes; unknown keys fail.
Properties and set/get use the same storage. Command options override settings;
running jobs retain their startup policy. Shell commands inherit check and can
override it per call; interactive prompt input is not an exit-status check.
Session logging never changes the shared logger level; application handler
filters/levels still apply. Verbose explicitly prints command output and may
expose sensitive output. No console logging handler is installed by Session.

Set `session.set(policy=paramiko.AutoAddPolicy())` or assign `session.policy`
to choose the missing-host-key policy for future connections (import `paramiko`
first). The default is `None`, retaining Paramiko's RejectPolicy. An explicit
`connect(policy=...)` wins for that connection; `connect(policy=None)` uses
default rejection. Children inherit the Session setting, even when a connection
uses an override. Settings dictionaries are copied, but policy objects are
shared; custom policies should support reuse. Existing connections keep their
original policy.

<a id="foreground-jobs-in-persistent-consoles-unreleased"></a>

## Foreground jobs in persistent consoles (4.0)

`console.start(command)` and `$.start(command)` inside shell/sudo/su return a
CommandJob in the current Bash console, retaining cwd/environment/identity.
Ordinary calls still return completed CommandResult snapshots. Each console
permits one foreground job; use its stream/wait/stop methods before issuing
another command. Console jobs default to a 60-second total deadline. PTY stop
requests Ctrl-C and verifies recovery to the original UID/PID; an unresolved
recovery disables the channel. Pipe consoles cannot safely cancel a running job.
See [console foreground jobs](API_GUIDE.md#unreleased-foreground-jobs-inside-shell-sudo-and-su)
for executable examples, quoting, thread ownership and failure handling.

<a id="managed-deadlines-and-long-running-commands-unreleased"></a>

## Managed deadlines and long-running commands (4.0)

The source checkout adds a total deadline shared by local and SSH commands:

```python
result = session.exec_command(["uname", "-s"], command_timeout=30, check=True)
```

This opt-in path returns `JobResult` (a `CommandResult` subclass), retains at
most 1 MiB of output per stream by default, and raises `CommandTimeoutError`
with partial output on expiry. `command_timeout=None` selects managed execution
without a deadline. Legacy `exec_command(timeout=...)` keeps its existing
backend-specific behavior; do not combine the two parameters.

Use `Session.start()` for a command that runs until its user stops it:

```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    with local.start(["tcpdump", "-l", "-n", "-i", "eth0"],
                     timeout=None, stop_timeout=5, check=True) as capture:
        try:
            for chunk in capture.iter_stdout():
                print(chunk, end="", flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            result = capture.stop()
        print("\nTermination:", result.termination_status)
```

Choose an interface on your host and run under an account authorized to capture
packets. `start(timeout=...)` always means a total command budget; `None` means
no deadline. Local stop sends SIGINT to the owned process group, then escalates
after `stop_timeout`. Remote stop can attempt Ctrl-C with `get_pty=True`, but
closing an SSH channel alone does not prove termination: inspect
`termination_status`. A job context and `Session.close()` clean up active jobs.
Streaming yields chunks, with bounded buffering and explicit overflow errors.

See [Timeouts, cancellation, tcpdump, and cleanup](https://iapyeh.github.io/sshscript/v3a/security-and-operations/timeouts-retries-and-cleanup/)
for the timing contract, remote example, output limits, and migration details.
These new APIs are not present in the published 3.1.5 package.

<a id="session-lifetime-unreleased-close-safeguards"></a>

## Session lifetime (4.0 close safeguards)

Use console and remote Session contexts to manage their scoped resources.
A local `with Session()` activates a reusable Session; leaving that block does
not close it. Use `contextlib.closing(Session())` when the outer scope should
also release the local Session, as shown in the canonical API guide.

To permanently stop using a Session, leave its console contexts first, then
call `close()` (or `close(strict=True)` to raise on cleanup failure). Closing a
Session with an active shell/su/sudo/enter context on itself or a descendant
raises `RuntimeError` before any cleanup or state change, even with
`strict=False`. Return from a function or propagate an exception to leave a
console early. Closing a child Session leaves its parent usable.

After close, new work is rejected; repeated close calls retain the cleanup
outcome. `closed=True` means the Session is disabled, while the close return
value and `close_errors` report whether all cleanup succeeded.

## First secure SSH connection

SSHScript uses Paramiko and verifies system host keys by default. Before the
first connection, place the server key in the account's standard
`known_hosts` file and verify its fingerprint through an independent trusted
channel. Prefer an SSH agent, managed private key, or secret manager over a
password embedded in source code.

```python
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
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
[SSHScript documentation](https://iapyeh.github.io/sshscript/v3a/) for
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
from contextlib import closing
from sshscript import Session

# Inspect effective settings without connecting or starting a proxy process.
settings = Session.resolve_connection("production", port=2222)

with closing(Session()) as local:
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

The regular Python Session API and optional `.spy` syntax share execution
semantics. Save this as `health.spy` (Dollar syntax is not ordinary Python):

```spy
result = $(["printf", "%s", "ready"], check=True)
print(result.stdout)
```

Run it with `sshscript health.spy`; expected output is `ready`. This is a
single-command example using the published 3.1.5 API, not the library test gate.

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

The credential-free library gate is `python3 tools/run_checks.py`. A source
checkout keeps modules and `unittest/` at the root; a release checkout uses
`src/sshscript/`. The tools detect both layouts. From either repository root:

```sh
python3 -m pip install 'paramiko>=2.11,<5' 'packaging>=21' build twine
python3 tools/run_checks.py
python3 tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE
```

The output directory must not already exist. `run_checks.py` locates the test
suite under `unittest/` or `src/sshscript/unittest/` automatically. See the
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
