---
title: "Installation and Verification"
parent: "Getting Started"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
permalink: /v3a/getting-started/installation-and-verification/
---

# Installation and Verification

This page installs the version intended by these documents and verifies both
the command-line program and Python import before any SSH connection is made.

## Version status

> **SSHScript v3.1 is currently beta source, not a PyPI release.** As of this
> page's update, the [SSHScript project on PyPI](https://pypi.org/project/sshscript/)
> publishes v2.0.2, so `python3 -m pip install sshscript` does not install the
> complete v3.1 API documented on this site.

Do not use an unqualified PyPI installation while following the v3.1
documentation. The v3.1 release notes and installation instructions will be
updated when a packaged release is published.

## Requirements

The prepared v3.1 source declares:

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

## Install the v3.1 beta source

> **Public-installation blocker:** the public repository does not yet provide
> a tagged v3.1 artifact with committed packaging metadata. Consequently this
> page cannot yet give ordinary users a public, reproducible checkout command.
> Do not substitute an unverified branch, archive, or PyPI package.

If you have been given an authorized v3.1 source checkout or archive that
contains its packaging metadata, install it from that source directory:

```sh
test -f pyproject.toml
python3 -m pip install .
```

Contributors who intentionally need an editable checkout may instead use
`python3 -m pip install -e .`. Do not advertise a Git URL as a reproducible
v3.1 installation until the public branch contains the required packaging
metadata and an immutable tag or commit has been identified.

When v3.1 is published to PyPI, the release installation will use a bounded
requirement such as:

```sh
python3 -m pip install "sshscript>=3.1,<3.2"
```

That command is shown for the future release and is **not** the current beta
installation method.

## Verify the command-line program

```sh
sshscript --version
```

Expected output:

```text
3.1.0
```

If the command is missing, make sure the virtual environment is active. If it
prints another version, stop and identify the environment before running v3.1
examples.

## Verify the Python import

```sh
python3 -c "import sshscript; print(sshscript.__version__); print(sshscript.__file__)"
```

The first line must be `3.1.0`. The second line identifies the package being
imported; for an editable installation it should point into the intended v3.1
checkout. This catches a common problem in which an older installation or a
local `sshscript.py` file shadows the intended package.

## Verify the dependency set

```sh
python3 -m pip check
python3 -m pip show sshscript paramiko packaging
```

`pip check` should report no broken requirements. Keep this output when
reporting installation problems, together with the operating system and
Python version. Remove usernames, private paths, tokens, and credentials
before posting diagnostics publicly.

## About the update checker

```sh
sshscript --check-updates
```

`--check-updates` (with `--check` as an alias) queries stable releases on
PyPI. It does not install anything and it is not a beta-version verifier.
While v3.1 remains unpublished, it can correctly report v2.0.2 as the newest
stable PyPI release even when the installed beta reports `3.1.0`.

## Next step

Continue with the [5-Minute Quickstart](../quickstart/) to execute a
credential-free command. See
[Installation Troubleshooting]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/troubleshooting-installation/)
if the
version or import path is not what you expect.

Last Updated: 2026-09-21 17:45:03
