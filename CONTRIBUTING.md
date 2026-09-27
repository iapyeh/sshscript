# Contributing

Thank you for helping improve SSHScript. Participation is governed by the
[Code of Conduct](CODE_OF_CONDUCT.md). Please use a private security advisory,
not an issue or pull request, for a suspected vulnerability.

## Development setup

Use Python 3.11 or newer. The public release checkout uses a `src/` package
layout. From the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
python3 -m pip install build twine
```

Keep test credentials, host inventories, local configuration, build output,
and editor state untracked.

## Required checks

Run the complete credential-free gate before proposing a change:

```sh
python3 tools/run_checks.py
python3 tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE
```

The output path must not already exist. The first command finds the public test
suite under `src/sshscript/unittest/` and runs normal and optimized tests,
compile checks, the package assertion scan, and dollar-syntax smoke tests. The
second command builds the allowlisted wheel and source distribution, checks
their metadata, installs the wheel in an isolated environment, and performs an
installed-package smoke test.

Tests under `src/sshscript/unittest/` must not require network access, SSH
agents, private keys, passwords, or host-specific configuration unless they are
part of the isolated OpenSSH fixture. A regression fix should add a
credential-free test whenever the behavior can be reproduced with a fake
Paramiko client or local subprocess.

## SSH integration tests

Public CI provisions a disposable loopback OpenSSH server and runs
`src/sshscript/unittest/test_openssh_integration.py` against the built wheel.
The setup uses ephemeral users, passwords, and keys generated inside the CI
runner; it must never target a persistent host. See
`tools/setup_openssh_ci.sh` for the exact environment contract.

Historical site-specific and credentialed tests are intentionally not shipped
in the public release checkout. Do not add production credentials or internal
host scenarios to a pull request. Convert a failure into a disposable fixture,
redacted fake, or credential-free unit test first.

## Compatibility and public APIs

Changes to `Session`, `run_file()`, CLI exit statuses, dollar syntax, logging,
or SSH security defaults require synchronized implementation, tests, README,
and changelog updates. Avoid silently accepting insecure behavior.

The module API is the primary public interface. Keep dollar syntax behavior
aligned with it, and document compatibility aliases or deprecations explicitly.
Tests should cover both normal Python and `python -O` where the exception
contract is involved. Do not use runtime `assert` statements for package input
or lifecycle validation.

Before release, run all normal, optimized, compile, and AST gates listed in
[EXCEPTIONS.md](EXCEPTIONS.md). CI targets Python 3.11 through 3.14.

## Pull requests

Target the protected `release` branch from a topic branch or fork. Keep each
pull request focused and include:

- the problem and intended behavior;
- tests that fail before the change and pass afterward when practical;
- documentation and changelog updates for user-visible behavior;
- the commands used to validate the change;
- any compatibility, security, logging, or migration impact.

Complete the pull request template and respond to review feedback. A passing CI
run is required but does not guarantee acceptance. By submitting a
contribution, you agree that it may be distributed under the repository's MIT
License.
