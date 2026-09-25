---
title: "Installation and Verification"
parent: "Getting Started"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
permalink: /v3a/getting-started/installation-and-verification/
---

# Installation and Verification

This page installs the supported SSHScript release and verifies the command-line
program, Python import, and dependency set before any SSH connection is made.

## Version status

> **SSHScript 3.1.4 is the current Production/Stable release.** It is available
> from [PyPI](https://pypi.org/project/sshscript/3.1.4/) and the corresponding
> [GitHub Release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.4).
> These documents cover the supported 3.1.x line and were last verified with
> 3.1.4.

## Requirements

SSHScript 3.1.4 declares:

- Python 3.11 or newer;
- macOS or a POSIX Linux environment;
- Paramiko 2.11 or newer, but earlier than 5; and
- Packaging 21 or newer.

Windows is not currently listed as a supported platform. The local runner must
use a supported POSIX environment. Remote one-shot commands require a
POSIX-compatible SSH command environment; `shell()`, `su()`, and `sudo()` also
require the corresponding Unix tools. Other remote operating systems are not
part of the documented v3.1 contract.

## Create an isolated environment

Use the same Python executable to create the virtual environment and invoke
`pip`:

```sh
python3 --version
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
```

Confirm that the selected interpreter is Python 3.11 or newer before
continuing.

## Install from PyPI

For an ordinary installation, install the current stable release:

```sh
python3 -m pip install sshscript
```

For a deployment that must remain reproducible, pin the exact release in the
environment's requirements or lock file:

```sh
python3 -m pip install "sshscript==3.1.4"
```

To accept future compatible maintenance releases within the supported line,
use `sshscript>=3.1.4,<3.2` and preserve the resolver output in a lock file.
Do not rely on an unbounded dependency in a production deployment.

## Install the tagged source

Ordinary users should prefer the PyPI wheel. Contributors who need to inspect
or test the released source can use the immutable release tag:

```sh
git clone --branch v3.1.4 --depth 1 https://github.com/iapyeh/sshscript.git
cd sshscript
python3 -m pip install .
```

The mutable `release` branch is useful for development but is not a
reproducible version selector. Use a tag or full commit SHA when a source
installation must be auditable.

## Verify the command-line program

```sh
sshscript --version
```

Expected output:

```text
3.1.4
```

If the command is missing, make sure the virtual environment is active. If it
prints another version, stop and identify the environment before running v3.1
examples.

## Verify the Python import

```sh
python3 -c "import sshscript; print(sshscript.__version__); print(sshscript.__file__)"
```

The first line must be `3.1.4`. The second line identifies the package being
imported and should point into the active virtual environment for a PyPI
installation. This catches a common problem in which an older installation or
a local `sshscript.py` file shadows the intended package.

## Verify the dependency set

```sh
python3 -m pip check
python3 -m pip show sshscript paramiko packaging
```

`pip check` should report no broken requirements. Keep this output when
reporting installation problems, together with the operating system and
Python version. Remove usernames, private paths, tokens, and credentials
before posting diagnostics publicly.

## Verify release provenance

The 3.1.4 distributions were built and tested by the repository's public
release workflow. The workflow:

1. runs the credential-free checks and package assertion gate;
2. builds and verifies one wheel and one source distribution;
3. exercises the installed wheel against a disposable OpenSSH server;
4. records SHA-256 hashes and GitHub build-provenance attestations;
5. publishes to PyPI with a short-lived OIDC credential from the configured
   Trusted Publisher; and
6. publishes the GitHub Release only after PyPI accepts the distributions.

Review the [v3.1.4 release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.4),
the [successful release workflow](https://github.com/iapyeh/sshscript/actions/runs/35963068790),
and PyPI's distribution metadata before adopting an artifact. Provenance
confirms where an artifact came from; it does not replace source review or
site-specific validation.

## About the update checker

```sh
sshscript --check-updates
```

`--check-updates` (with `--check` as an alias) queries stable releases on
PyPI that are compatible with the current Python version. It does not install
anything. Verify the installed version and import path separately as shown
above.

## Upgrade an existing installation

Upgrade within the supported 3.1 line with:

```sh
python3 -m pip install --upgrade "sshscript>=3.1.4,<3.2"
sshscript --version
python3 -m pip check
```

Review the release notes and repeat application-specific SSH, PAM, `sudoers`,
network, and host-key tests before promoting an upgraded environment.

## Next step

Continue with the [5-Minute Quickstart](../quickstart/) to execute a
credential-free command. See
[Installation Troubleshooting]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/troubleshooting-installation/)
if the
version or import path is not what you expect.

Last Updated: 2026-09-24 15:36:45
