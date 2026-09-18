---
title: "SSHScript v3.1"
nav_exclude: true
---

# SSHScript v3.1

SSHScript brings local commands, SSH automation, and Python control flow into
one programming model. Its primary interface is the regular Python `Session`
API, while the optional Dollar syntax offers concise notation for standalone
`.spy` scripts.

> **Release status:** SSHScript v3.1 is beta source and is not currently
> published on PyPI. The unqualified `pip install sshscript` command presently
> installs v2.0.2. Follow the version-specific installation page before using
> examples from this site.

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
   and confirm that both the CLI and import report `3.1.0`.
2. Complete the credential-free [5-Minute Quickstart](getting-started/quickstart/).
3. Continue with the
   [Module API Tutorial](SSHScript%20v3%20Documents/tutorial/).
4. Use the [SSHScript v3.1 Documentation](SSHScript%20v3%20Documents/)
   sidebar for task guides, concepts, reference, security, and migration.

The documentation is English-first. Visible placeholders are intentional:
they identify planned coverage without implying that an unfinished page is
complete. The [Example Gallery](Example%20Gallery/) remains a placeholder
catalog for future, tested operational recipes.

## Project status

SSHScript v3.1 is beta software. Run the credential-free release gate before
deployment and validate real SSH behavior in an isolated test environment
before production rollout. SSHScript is released under the MIT License.

Last Updated: 2026-09-18 15:58:44
