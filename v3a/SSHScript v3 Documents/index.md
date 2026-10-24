---
title: "SSHScript Documentation"
nav_order: 1
has_children: true
has_toc: false
---

# SSHScript Documentation

> **7.0.0 source contract.** Use the matching source checkout or verified wheel.
> A source push does not publish a GitHub Release or PyPI package.

> **Development status: not stable.** SSHScript is under active development.
> APIs, CLI options, configuration and data formats may change incompatibly
> without a deprecation period. Pin the exact version or source revision,
> review changes before upgrading, and validate your automation again.


SSHScript aims to help engineers and AI agents execute, understand, and hand
off automation reliably. Use the regular Python Session API first; optional
Dollar syntax shares the same execution semantics. Retain the command's host,
output, status and installed version, distinguish failure from timeout, and
reconcile unknown termination. A zero exit status does not prove deployment
success; closing an SSH channel does not prove its remote process stopped.

The credential-free example baseline is **3.1.5**. Current connection examples
use the **7.0.0 source contract**, including keyword-only options and
the new snake_case connection names. The previously published **6.1.0** package has the earlier names;
a documentation or source update does not publish a new package. See
[version policy and connection changes]({{ site.baseurl }}/v3a/migration-and-releases/version-policy/)
before selecting a matching checkout or artifact.

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

*Last modified: 2026-10-24 16:35:46*

Last Updated: 2026-10-24 16:35:46
