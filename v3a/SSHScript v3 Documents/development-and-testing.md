---
title: "Contributing and Testing"
parent: "SSHScript Documentation"
nav_order: 9
---

# Contributing and Testing

> **Version scope:** The argv/CommandResult/check/config API is available in 3.1.5.
> Session settings and managed jobs/deadlines are features available in 4.0.2.
> Use the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/) to choose
> examples for your installed version.

SSHScript v3.1 separates credential-free release checks and public disposable
OpenSSH integration from manual, site-specific SSH tests. The default gate must
work on a clean developer machine without a network connection, SSH agent,
private key, password, or host inventory.

## Development setup

Use Python 3.11 or newer. Clone the public release branch, then create an
isolated environment for its test and build dependencies:

```sh
git clone --branch release --single-branch https://github.com/iapyeh/sshscript.git
cd sshscript
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install 'paramiko>=2.11,<5' 'packaging>=21' build twine
```

Contributors normally work in a personal fork and propose changes through a
pull request. Do not add credentials, private host inventories, or captured
production output to the checkout.

## Required checks

Run the canonical credential-free gate from the public repository root before
proposing a change:

```sh
python3 tools/run_checks.py
```

The tool locates the release package under `src/sshscript`, then runs the
normal and optimized unit suites, compilation, the Dollar-syntax smoke suite,
and the package assertion scan from the correct working directory. The
low-level tests reside under `src/sshscript/unittest`; invoking the tool avoids
instructions that work only in the project's separate internal development
layout. A regression fix should add a credential-free test whenever the
behavior can be reproduced with a local subprocess, in-memory SSH client, or
Paramiko test double.

## Credential-free Module API tests

`src/sshscript/unittest/test_sshscript_module.py` verifies the regular Python
API, and `src/sshscript/unittest/test_spy_thread_session.py` verifies Session
inheritance in transformed `.spy` threads. The tests cover:

- import-time isolation for process hooks, warnings, logging, and threads;
- explicit and reversible imports through `sshscript.spy_imports()`;
- importing and constructing the public `Session` class;
- side-effect-free construction and scoped session-stack activation;
- local Session lifecycle and repeatable cleanup;
- string commands assembled with `shlex.join()`, stdin, environment
  variables, stdout, stderr, and exit codes;
- automatic and explicit shell selection;
- invalid command types and empty commands;
- `run_script()` and single-file `run_file()` behavior;
- independent local Sessions in worker threads; and
- connected Session inheritance in `.spy` threads using in-memory SSH
  clients.

The suite uses Python's standard `unittest` framework plus SSHScript's normal
runtime dependencies. No separate test framework is required.

## Credential-free Dollar syntax tests

`src/sshscript/unittest/dollar_syntax.spy` is a localhost-only smoke suite run
by `python3 tools/run_checks.py` from the public repository root.

It covers bare, string, raw-string, expression, and f-string command forms;
result properties; automatic shell selection; string/argv command
validation; function bodies; persistent shell contexts; and imports between
`.spy` files.

Its standard-library wrapper runs the suite in an isolated subprocess with an
empty temporary home directory and SSH-agent variables removed. Use the
canonical gate instead of copying its internal discovery commands; this keeps
local validation aligned with CI as the test set changes.

## Language and integration tests

`src/sshscript/unittest/language.spy` provides an additional maintainer
diagnostic for extended syntax on localhost. From the public repository root:

```sh
(cd src/sshscript && python3 sshscript.py unittest/language.spy --environment=local)
```

Its coverage includes one-Dollar replacements for former `$$` behavior,
quote-aware shell selection, explicit shell overrides, results, functions,
persistent shell contexts, `enter()`, and imports between `.spy` modules.
Temporary filesystem assertions use unique paths and clean up in `finally`
blocks.

Historical remote modes require private, site-specific configuration and are
not part of the public release gate. New portable SSH coverage belongs in the
disposable OpenSSH integration suite. Keep any additional host configuration
in ignored local files or environment variables. Public documentation and
committed tests must not contain real usernames, host inventories, key paths,
passwords, or captured secrets.

## Credentialed test safety

Maintainers may keep separate, untracked site-specific scenarios that connect
to real hosts, change privileges, transfer files, or run administrative
commands. These are not part of the public repository or release gate. Before
running such tests:

- use disposable test hosts;
- inspect every command for destructive effects;
- keep credentials and inventories outside version control; and
- verify failures in the main process, including failures raised by worker
  threads.

Credentialed success does not excuse a failing credential-free gate. Both
layers must be healthy before release.

## Compatibility and public APIs

Changes to `Session`, `run_file()`, CLI exit statuses, Dollar syntax,
logging, or SSH security defaults require synchronized implementation,
tests, public documentation, and release notes. Avoid silently accepting
insecure behavior.

## Supported matrix and assertion gate

CI targets Python 3.11, 3.12, 3.13, and 3.14 on Linux and macOS. All eight
platform/interpreter combinations passed both normal and optimized checks for
the 3.1.4 release. Disposable OpenSSH integration jobs also passed on Python
3.11 and 3.14. Every new candidate must pass its own current
workflow; an earlier green release does not validate later changes. The
dependency-free AST gate rejects `ast.Assert` in shipped package modules,
excluding tests. Regression tests use unittest assertions so validation
remains meaningful under `-O`. Private historical integration material is not
part of the credential-free gate and must not be bulk-added to Git.

## Release layout and artifact verification

Run `python3 tools/run_checks.py` from the public repository root. It selects
the release package source directory and runs the normal and optimized tests,
Dollar syntax checks, compilation, and assertion scan.

```sh
python3 tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE
```

Choose a new output directory each time. The command prepares an allowlisted
source tree, builds an sdist and then its wheel, runs strict metadata checks,
and installs the wheel in a fresh virtual environment outside the source tree.
It verifies the module version, CLI, and local command execution. Build and
installation steps need network access for dependencies; runtime tests do not
need SSH credentials. Successful verification saves both distributions and a
`verified.json` SHA-256 manifest.

Release preparation uses `tools/prepare_release.py` and an explicit file
allowlist so private integration tests, credentials, and unrelated files are
excluded. Project maintainers should follow
[the release procedure](https://github.com/iapyeh/sshscript/blob/release/RELEASING.md).

GitHub Actions runs these checks on Linux/macOS and Python 3.11–3.14 for pushes
and pull requests. Separate Linux jobs install the verified wheel and exercise
host keys, SFTP, PTY behavior, `sudo`/`su`, and timeouts against a disposable
OpenSSH server. Check the actual workflow results before declaring a candidate
validated on every platform.

Production publication is performed only by the tag-triggered
`.github/workflows/release.yml` workflow. It verifies that `v<version>` points
to the current `release` branch tip and matches package metadata, rebuilds and
tests the distributions, attests them, creates a draft GitHub Release,
publishes to PyPI through its Trusted Publisher with a short-lived OIDC
credential, and then makes the GitHub Release public. `verified.json` is
retained with the release assets. Manual upload is an emergency-only path;
it must verify the recorded hashes and use credentials supplied by an external
secret manager.

## New command/config/check regression coverage

The credential-free suite covers argv boundaries (empty arguments, quotes,
newlines, and shell metacharacters), three-value unpacking/indexing, immutable
results after subsequent commands, local/fake-SSH failure capture, configuration
overrides and proxy command construction, and compile-only scripts with no user
code or import side effects. Source mapping tests include functions, multiline
expressions, imported `.spy` modules, and tokenizer indentation failures.

<a id="transport-and-resource-boundaries-400dev0-unreleased"></a>

## Transport and resource boundaries (4.0.2, 4.0)

The development candidate adds regressions for execution contracts that humans
and AI can inspect: exact input, retained output, completion versus transport
failure, and ownership of resources. These tests are not evidence that an
application's deployment succeeded.

`test_command_job.py` uses real Paramiko transports over a socketpair and
forwards stdin to a real child process. A 32 KiB SSH window forces flow control.
The bulk test sends more than 512 KiB of binary/Unicode input while the child
first emits 256 KiB on each output stream before reading input. It compares
complete output, input SHA-256, byte count and EOF across local/SSH backends,
legacy calls, managed calls and `start()`. Empty input has a separate EOF test.

The same suite checks missing SSH exit status, transport loss after observed
output, rejection of local execution fallback, and a usable parent/shared
transport after a command channel closes. Three cycles per backend of
completion, cancellation and timeout check owned worker threads, local
processes/pipes and SSH channels. Fixture teardown joins server/transport
workers and checks descriptor counts where `/proc/self/fd` or `/dev/fd` exists.
The fixture explicitly kills surviving test processes; that housekeeping does
not prove that closing an SSH channel killed a remote process. A remote stop
without termination evidence remains `termination_status="unknown"`.

`test_openssh_integration.py` adds native OpenSSH coverage for more than 4 MiB
of input, 3 MiB on each output stream before input is read, EOF, execution-time
disconnection, nested SSH and ProxyJump. Tests check child/proxy resource
cleanup, preservation of the parent connection and rejection of an unknown
jump-host key with strict host-key checking.

The candidate CI and release transport jobs select these dependency cases:

| Python | Paramiko |
| --- | --- |
| 3.11 | 2.11.0, the package metadata minimum |
| 3.14 | 2.11.0 |
| 3.11 | current 3.x |
| 3.14 | current 4.x |

Installation explicitly keeps the selected dependency when installing the
wheel. CI verifies source and extracted-sdist checks under that dependency,
then runs native tests against the installed artifact outside the checkout.
Release jobs test the built wheel under the same selected dependency cases.
See `unittest/README.module-tests.md` in the candidate source distribution for
focused commands and disposable Linux provisioning instructions.

For local candidate commit `59c33e4`, normal and optimized source/sdist runs
each discovered 278 tests and passed with 24 native cases skipped. Selected
macOS OpenSSH regressions passed in eight-case runs, including an actual-wheel
run. These are local observations: the expanded Linux GitHub Actions matrix
has not yet run for this candidate. Skips and matrix definitions are not passing
evidence. The selected transport tests do not establish complete PAM/su/sudo
compatibility, every network failure, or long-duration resource stability;
the three-cycle cleanup regression is not a long-term soak test.

## Native privilege authentication evidence

The 4.0 native authentication gate exercises actual su/sudo, PAM and
sudoers on disposable Ubuntu accounts. It uses the candidate wheel with local
subprocess and loopback OpenSSH backends. Cases check target UID, parent shell
UID/PID restoration, wrong/missing passwords, policy rejection, passwordless
entry, and deadlines. A failure must exclude the block body; an unconfirmed
recovery must make the channel reject further work.

CI and release jobs save JSON evidence with the wheel SHA-256, platform/tool
versions, individual case results and observed recovery outcomes. Review the
actual candidate's report before calling it validated: a configured CI job or
skipped native tests are not passing evidence. This supports SSHScript's role as
an execution layer that engineers and AI can inspect and hand off reliably.

See `unittest/README.console-authentication.md` in the source distribution for
reproducible disposable-host commands. Normal test discovery skips native cases
and never requests workstation passwords or changes host accounts. Native
macOS, FreeBSD, BusyBox and site-specific PAM/sudo policies remain unverified
until corresponding reports exist; the macOS unit job does not establish native
privilege-authentication compatibility.

Last Updated: 2026-10-09 10:40:03
