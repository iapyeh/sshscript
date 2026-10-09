---
title: "SSHScript v3.1"
nav_exclude: true
---

# SSHScript v3.1

SSHScript aims to help engineers and AI agents execute, understand, and hand
off automation reliably. Use the regular Python Session API first; optional
Dollar syntax shares the same execution semantics. Retain the command's host,
output, status and installed version, distinguish failure from timeout, and
reconcile unknown termination. A zero exit status does not prove deployment
success; closing an SSH channel does not prove its remote process stopped.

The published example baseline is **3.1.5**. The current production
contract is **4.0.1**, with incompatible changes from 3.1.5; see
[version policy and migration]({{ site.baseurl }}/v3a/migration-and-releases/version-policy/).
Start with the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/)
for version-labelled examples and lifetime rules.

## Why SSHScript?

Use the same Session model to run a command on localhost, connect to a remote
host, enter a privileged or interactive context, transfer files, and return
cleanly through nested context managers. Python remains available for data
processing, branching, exceptions, testing, and integration with existing
applications.

SSHScript v3.1 emphasizes predictable and secure automation:

- one-shot commands accept nonempty strings or argv lists/tuples;
- argument sequences preserve data boundaries without caller-side quoting;
- results unpack as stdout, stderr, exitcode and retain per-command metadata;
- SSH host keys are verified by default; and
- imports, threads, and script execution remain scoped instead of changing
  process-wide Python behavior.

## Start here

1. Read [Installation and Verification](getting-started/installation-and-verification/)
   and confirm that both the CLI and import report `4.0.1`.
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

The current 4.0.1 release is classified Production/Stable for Python
3.11–3.14 on Linux and macOS. It introduces an incompatible execution contract;
review the migration guide before upgrading 3.1.5 automation. Review the candidate's CI
reports and validate site-specific PAM, `sudoers`, network, and host-key policy
in an isolated environment before rollout. SSHScript is released under the
MIT License.

## Trust and support

- Review the public [CI matrix](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml)
  and the [published baseline release](https://github.com/iapyeh/sshscript/releases/tag/v3.1.5).
- Read the [security policy](https://github.com/iapyeh/sshscript/blob/release/SECURITY.md)
  before reporting a vulnerability.
- Use the [support policy](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)
  to choose between documentation, Discussions, Issues, and private
  vulnerability reporting.
- Consult the
  [production checklist](security-and-operations/failure-model-and-production-checklist/)
  before privileged or destructive rollout.

Last Updated: 2026-10-08 23:46:37
