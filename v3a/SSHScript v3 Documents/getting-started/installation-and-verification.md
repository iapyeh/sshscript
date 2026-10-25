---
title: "Installation and Verification"
parent: "Getting Started"
grand_parent: "SSHScript Documentation"
nav_order: 1
permalink: /v3a/getting-started/installation-and-verification/
---

# Installation and Verification

> **Documentation contract: SSHScript 7.0.0.** Install the published 7.0.0
> package or the matching pinned source. Earlier packages have different
> connection parameter names; review version differences before upgrading.

## Requirements

SSHScript 7.0.0 requires Python 3.11+, a POSIX Linux or macOS runner,
Paramiko >=2.11,<5 and Packaging >=21. Native Windows is not supported;
use a supported POSIX environment. Remote shell and privilege operations also
require the corresponding tools and authentication policy on the target host.

If explicitly pinning Paramiko 2.11, also pin `cryptography<48`; that backend
imports TripleDES from a namespace removed in cryptography 48. The minimum CI
checks this compatible pair. Normal installations select the newer supported
Paramiko backend; do not impose this cryptography cap on those installations.

## Install the published version

Create an isolated environment and install SSHScript 7.0.0 from PyPI:

```sh
python3 --version
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install "sshscript==7.0.0"
```

When replacing an existing source installation with the same version number,
use `python3 -m pip install --force-reinstall "sshscript==7.0.0"` in the actual
execution environment. Restart processes that already imported SSHScript.
Pin transitive dependencies in your application's lock file as well.

## Install matching source instead

The [7.0.0 release](https://github.com/iapyeh/sshscript/releases/tag/v7.0.0)
corresponds to this immutable source commit:

```sh
python3 -m pip install --force-reinstall "git+https://github.com/iapyeh/sshscript.git@a1c76d016419484b6ffb930bf2b16f30bae61208"
```

Retain that full SHA when reproducing a source installation. A verified local
7.0.0 wheel can also be installed with
`python3 -m pip install /path/to/sshscript-7.0.0-py3-none-any.whl`.

For future PR/candidate snapshots, including installation of their matching
agent documents and complete skill, follow
[Testing an unreleased source snapshot]({{ site.baseurl }}/v3a/ai-agents/guide/#testing-an-unreleased-source-snapshot).
The same workflow covers returning to `release`.

## Verify CLI and import

```sh
sshscript --version
python3 -I -c "import sshscript; print(sshscript.__version__); print(sshscript.__file__)"
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

The [7.0.0 GitHub Release](https://github.com/iapyeh/sshscript/releases/tag/v7.0.0)
retains verified artifacts and their SHA-256 manifest. Compare those hashes
with the [7.0.0 PyPI files](https://pypi.org/project/sshscript/7.0.0/#files)
when verifying a downloaded distribution.

`sshscript --check-updates` queries compatible published PyPI versions and never
installs anything. It is independent of the source checkout's version. Upgrade
source installations by selecting and verifying a new full commit; update the
lock file and repeat your SSH, host-key, PAM and sudoers checks.

## Next step

Run the [5-Minute Quickstart]({{ site.baseurl }}/v3a/getting-started/quickstart/),
then use the [canonical guide]({{ site.baseurl }}/v3a/recommended-api/).

*Last modified: 2026-10-25 21:18:40*

Last Updated: 2026-10-25 21:18:40
