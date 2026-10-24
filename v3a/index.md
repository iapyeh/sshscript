---
title: "SSHScript 6.1.0"
nav_exclude: true
---

# SSHScript 6.1.0

SSHScript aims to help engineers and AI agents execute, understand, and hand
off automation reliably. Use the regular Python Session API first; optional
Dollar syntax shares the same execution semantics. Retain the command's host,
output, status and installed version, distinguish failure from timeout, and
reconcile unknown termination. A zero exit status does not prove deployment
success; closing an SSH channel does not prove its remote process stopped.

> **Development status: not stable.** SSHScript is under active development.
> APIs, CLI options, configuration and data formats may change incompatibly
> without a deprecation period. Pin the exact version or source revision,
> review changes before upgrading, and validate your automation again.

> Connection examples use the unreleased development API; published 6.1.0
> uses the previous parameter names. Use a matching checkout or artifact and
> read the [connection changes]({{ site.baseurl }}/v3a/migration-and-releases/version-policy/).


The current contract is **6.1.0**. The public
[Console integration API]({{ site.baseurl }}/v3a/reference/embedded-console/)
borrows an existing Session for terminal, host application or AI agent interaction.
It retains Python/shell/program state, reports structured readiness and results,
and makes credential hooks, layer ownership and Session reuse explicit. The CLI
uses the same implementation. Earlier 6.0 internal entry points and :help/:quit
aliases are removed; use Console(session), submit(), help/quit and structured updates.

Start with the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/)
for version-labelled examples and lifetime rules.

## Why SSHScript?

Use the same Session model to run a command on localhost, connect to a remote
host, enter a privileged or interactive context, transfer files, and return
cleanly through nested context managers. Python remains available for data
processing, branching, exceptions, testing, and integration with existing
applications.

SSHScript 6.1.0 emphasizes predictable and secure automation:

- one-shot commands accept nonempty strings or argv lists/tuples;
- argument sequences preserve data boundaries without caller-side quoting;
- results unpack as stdout, stderr, exitcode and retain per-command metadata;
- SSH host keys are verified by default; and
- imports, threads, and script execution remain scoped instead of changing
  process-wide Python behavior.

## Start here

For AI-assisted automation, share the
[SSHScript for AI Agents]({{ site.baseurl }}/v3a/ai-agents/) landing page.
It provides a copyable task prompt, reading order, plain-text guide and
portable skill download.

1. Read [Installation and Verification](getting-started/installation-and-verification/)
   and confirm that both the CLI and import report `6.1.0`.
2. Complete the credential-free [5-Minute Quickstart](getting-started/quickstart/).
3. Continue with the
   [Module API Tutorial](SSHScript%20v3%20Documents/tutorial/).
4. Use the [SSHScript Documentation](SSHScript%20v3%20Documents/)
   sidebar for task guides, concepts, reference, security, and migration.

The documentation is English-first. The current onboarding, tutorial,
how-to, concept, reference, security, migration, and troubleshooting pages
are available through the sidebar and search. The
[Example Gallery](Example%20Gallery/) teaches SSHScript through complete,
safety-labelled cases while keeping existing URLs stable. For the companion
operations management framework, see
[SSHScript Ops](https://github.com/iapyeh/sshscript-ops), which plans reusable
recipes, data formats, and maintenance workflows. Ops is currently an initial
documentation scaffold, without executable recipes or an implemented system.

## Project status

SSHScript remains a development-stage project. Python 3.11–3.14 on Linux and
macOS are covered by the CI matrix. Local/simulated and browser UI validation by
OpsFeast is separate from native SSH/PAM/su/sudo evidence. Consult the release CI
and validate site-specific authentication and trust policies before rollout.
SSHScript is released under the MIT License.

## Trust and support

- Review the public [CI matrix](https://github.com/iapyeh/sshscript/actions/workflows/ci.yml)
  and the [current release](https://github.com/iapyeh/sshscript/releases/latest).
- Read the [security policy](https://github.com/iapyeh/sshscript/blob/release/SECURITY.md)
  before reporting a vulnerability.
- Use the [support policy](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)
  to choose between documentation, Discussions, Issues, and private
  vulnerability reporting.
- Consult the
  [production checklist](security-and-operations/failure-model-and-production-checklist/)
  before privileged or destructive rollout.

*Last modified: 2026-10-24 13:19:20*

Last Updated: 2026-10-24 13:19:20
