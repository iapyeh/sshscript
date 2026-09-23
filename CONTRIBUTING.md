# Contributing

## Development setup

Use Python 3.11 or newer. The development checkout is a flat source tree, so
install its development dependencies rather than installing it in editable
mode:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install 'paramiko>=2.11,<5' 'packaging>=21' build twine
```

## Required checks

Run the complete credential-free gate before proposing a change:

```sh
python3 tools/run_checks.py
python3 tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE
```

Tests under `unittest/` must not require network access, SSH agents, private
keys, passwords, or host-specific configuration. A regression fix should add a
credential-free test whenever the behavior can be reproduced with a fake
Paramiko client or local subprocess.

## Credentialed integration tests

`unittest-v3/` contains historical and site-specific SSH scenarios. Treat them
as manual integration tests:

- run them only against disposable hosts;
- never commit credentials, keys, host inventories, or captured secrets;
- review commands for destructive effects before execution;
- use environment variables or ignored local files for configuration.

Credentialed tests are not evidence that the credential-free release gate may
fail. Both layers must be healthy before a release.

The public CI also provisions a disposable loopback OpenSSH server and runs
`unittest/test_openssh_integration.py` against the built wheel. The setup uses
ephemeral users, passwords and keys generated inside the CI runner; it must
never target a persistent host. See `tools/setup_openssh_ci.sh` for the exact
environment contract.

## Compatibility and public APIs

Changes to `Session`, `run_file()`, CLI exit statuses, dollar syntax, logging,
or SSH security defaults require synchronized implementation, tests, README,
and changelog updates. Avoid silently accepting insecure behavior.


Before release, run all normal, optimized, compile, and AST gates listed in
[EXCEPTIONS.md](EXCEPTIONS.md). CI targets Python 3.11 through 3.14.
