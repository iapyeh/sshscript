---
title: "SSHScript v3.1"
nav_exclude: true
---

# SSHScript v3.1

SSHScript brings local commands, SSH automation, and Python control flow into
one programming model. Its primary interface is the regular Python `Session`
API, while the optional Dollar syntax offers concise notation for standalone
`.spy` scripts.

> **Release status:** SSHScript 3.1.4 is the current Production/Stable release
> and is available from [PyPI](https://pypi.org/project/sshscript/3.1.4/) and
> [GitHub](https://github.com/iapyeh/sshscript/releases/tag/v3.1.4). These
> documents cover the supported 3.1.x line and were last verified with 3.1.4.

## Why SSHScript?

Use the same Session model to run a command on localhost, connect to a remote
host, enter a privileged or interactive context, transfer files, and return
cleanly through nested context managers. Python remains available for data
processing, branching, exceptions, testing, and integration with existing
applications.

SSHScript v3.1 emphasizes predictable and secure automation:

- commands are explicit non-empty strings;
- dynamic argument lists can be safely assembled with `shlex.join()`;
- SSH host keys are verified by default; and
- imports, threads, and script execution remain scoped instead of changing
  process-wide Python behavior.

## Start here

1. Read [Installation and Verification](getting-started/installation-and-verification/)
   and confirm that both the CLI and import report `3.1.4`.
2. Complete the credential-free [5-Minute Quickstart](getting-started/quickstart/).
3. Continue with the
   [Module API Tutorial](SSHScript%20v3%20Documents/tutorial/).
4. Use the [SSHScript v3.1 Documentation](SSHScript%20v3%20Documents/)
   sidebar for task guides, concepts, reference, security, and migration.

The documentation is English-first. The current onboarding, tutorial,
how-to, concept, reference, security, migration, and troubleshooting pages
are available through the sidebar and search. The
[Example Gallery](Example%20Gallery/) is an open collection: new operational
cases can be added as independent, safety-labelled pages without moving
existing URLs.

## Project status

SSHScript v3.1 is Production/Stable software for Python 3.11–3.14 on Linux and
macOS. The 3.1.4 release passed the public platform matrix and disposable
OpenSSH integration tests before OIDC publication to PyPI. Operators should
still validate site-specific PAM, `sudoers`, network, and host-key policy in
an isolated environment before production rollout. SSHScript is released
under the MIT License.

## Trust and support

- Review the public [CI matrix](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml)
  and the [v3.1.4 release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.4).
- Read the [security policy](https://github.com/iapyeh/sshscript/blob/release/SECURITY.md)
  before reporting a vulnerability.
- Use the [support policy](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)
  to choose between documentation, Discussions, Issues, and private
  vulnerability reporting.
- Consult the
  [production checklist](security-and-operations/failure-model-and-production-checklist/)
  before privileged or destructive rollout.

Last Updated: 2026-09-25 16:37:52
