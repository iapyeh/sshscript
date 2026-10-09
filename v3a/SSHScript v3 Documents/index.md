---
title: "SSHScript Documentation"
nav_order: 1
has_children: true
has_toc: false
---

# SSHScript Documentation

SSHScript aims to help engineers and AI agents execute, understand, and hand
off automation reliably. Use the regular Python Session API first; optional
Dollar syntax shares the same execution semantics. Retain the command's host,
output, status and installed version, distinguish failure from timeout, and
reconcile unknown termination. A zero exit status does not prove deployment
success; closing an SSH channel does not prove its remote process stopped.

The published example baseline is **3.1.5**. The current production
contract is **4.0.2**, with incompatible changes from 3.1.5; see
[version policy and migration]({{ site.baseurl }}/v3a/migration-and-releases/version-policy/).
Start with the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/)
for version-labelled examples and lifetime rules.

The documentation is organized by reader intent: start with a credential-free
success, then use task guides, concepts, and reference for exact contracts.

| Section | Purpose |
| --- | --- |
| [Getting Started]({{ site.baseurl }}/v3a/getting-started/) | Install the intended version and obtain the first successful result. |
| [Tutorials]({{ site.baseurl }}/v3a/tutorials/) | Learn the Module API first, then the optional Dollar syntax. |
| [How-to Guides]({{ site.baseurl }}/v3a/how-to-guides/) | Complete focused command, SSH, privilege, interactive, transfer, streaming, and concurrency tasks. |
| [Concepts]({{ site.baseurl }}/v3a/concepts/) | Understand lifecycle, execution modes, results, errors, and `.spy` transformation. |
| [Reference]({{ site.baseurl }}/v3a/reference/) | Look up public signatures, options, results, and exceptions. |
| [Security and Operations]({{ site.baseurl }}/v3a/security-and-operations/) | Prepare automation for failure, security review, and production operation. |
| [Example Gallery]({{ site.baseurl }}/v3a/Example%20Gallery/) | Learn SSHScript through complete, safety-labelled teaching cases. |
| [Migration and Releases]({{ site.baseurl }}/v3a/migration-and-releases/) | Update earlier code and review current and historical releases. |
| [Contributing and Testing](development-and-testing/) | Run the release gate and work on SSHScript itself. |
| [SSHScript for AI Agents]({{ site.baseurl }}/v3a/ai-agents/) | Share one URL, follow the agent reading order, or download the portable skill. |

English is the maintained navigation language for this phase; existing
translated files remain in source but are excluded from the published site and
sidebar. The Example Gallery uses an append-only, one-page-per-case structure
so future teaching cases can be published without reorganizing established
links. [SSHScript Ops](https://github.com/iapyeh/sshscript-ops) is the companion
project for reusable recipes and operations management workflows. It is
currently an initial documentation scaffold, without executable recipes or an
implemented management system.

Last Updated: 2026-10-09 20:13:20
