---
title: "Installation and Verification"
parent: "Getting Started"
grand_parent: "SSHScript Documentation"
nav_order: 1
permalink: /v3a/getting-started/installation-and-verification/
---

# Installation and Verification

> **7.0.0 source contract.** This page installs the current source branch.
> A source push does not create a GitHub Release, tag or PyPI package.
> The previously published 6.1.0 package has different connection parameter names.

## Requirements

SSHScript 7.0.0 requires Python 3.11+, a POSIX Linux or macOS runner,
Paramiko >=2.11,<5 and Packaging >=21. Native Windows is not supported;
use a supported POSIX environment. Remote shell and privilege operations also
require the corresponding tools and authentication policy on the target host.

If explicitly pinning Paramiko 2.11, also pin `cryptography<48`; that backend
imports TripleDES from a namespace removed in cryptography 48. The minimum CI
checks this compatible pair. Normal installations select the newer supported
Paramiko backend; do not impose this cryptography cap on those installations.

## Install the matching source

Create an isolated environment and install from the release source branch:

```sh
python3 --version
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
git clone --branch release --depth 1 https://github.com/iapyeh/sshscript.git
cd sshscript
git rev-parse HEAD
python3 -m pip install .
```

Record the full commit SHA. The release branch can move; use the recorded full
SHA when reproducing the installation. A verified local 7.0.0 wheel can also be
installed with `python3 -m pip install /path/to/sshscript-7.0.0-py3-none-any.whl`.
Do not assume `pip install sshscript` from PyPI provides the current source API.
Pin transitive dependencies in your application's lock file as well.

## Verify CLI and import

```sh
sshscript --version
python3 -c "import sshscript; print(sshscript.__version__); print(sshscript.__file__)"
python3 -m pip check
python3 -m pip show sshscript paramiko packaging
```

Both version outputs must be **7.0.0**. The import path should point into the
active environment. Resolve a different version or a shadowing local module
before using the examples. The credential-free quickstart retains its labelled
3.1.5 baseline; connection names in the current guide require 7.0.0.

## Verify provenance and upgrades

Review the source commit, [CI workflow](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml),
[version differences]({{ site.baseurl }}/v3a/migration-and-releases/version-policy/)
and artifact hash before adopting an installation. Publishing a source branch
or passing local checks does not establish that native SSH/PAM/sudo behavior
works in your environment. Repeat site-specific validation before rollout.

The separately published [6.1.0 release](https://github.com/iapyeh/sshscript/releases/tag/v6.1.0)
and [PyPI metadata](https://pypi.org/project/sshscript/) describe those packages;
they do not establish publication or provenance of 7.0.0 artifacts.

`sshscript --check-updates` queries compatible published PyPI versions and never
installs anything. It is independent of the source checkout's version. Upgrade
source installations by selecting and verifying a new full commit; update the
lock file and repeat your SSH, host-key, PAM and sudoers checks.

## Next step

Run the [5-Minute Quickstart]({{ site.baseurl }}/v3a/getting-started/quickstart/),
then use the [canonical guide]({{ site.baseurl }}/v3a/recommended-api/).

*Last modified: 2026-10-24 16:46:57*

Last Updated: 2026-10-24 16:46:57
