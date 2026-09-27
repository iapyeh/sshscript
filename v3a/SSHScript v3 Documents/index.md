---
title: "SSHScript v3.1 Documentation"
nav_order: 1
has_children: true
has_toc: false
---

# SSHScript v3.1 Documentation

> **Next-release API:** This page describes the updated source checkout.
> The published 3.1.4 wheel retains the earlier command/config/check behavior.

The v3.1 documentation is organized by reader intent. Start with a verified,
credential-free success; move to task-oriented guides; use concepts to
understand behavior; and use reference pages for exact contracts.

| Section | Purpose |
| --- | --- |
| [Getting Started]({{ site.baseurl }}/v3a/getting-started/) | Install the intended version and obtain the first successful result. |
| [Tutorials]({{ site.baseurl }}/v3a/tutorials/) | Learn the Module API first, then the optional Dollar syntax. |
| [How-to Guides]({{ site.baseurl }}/v3a/how-to-guides/) | Complete focused command, SSH, privilege, interactive, transfer, streaming, and concurrency tasks. |
| [Concepts]({{ site.baseurl }}/v3a/concepts/) | Understand lifecycle, execution modes, results, errors, and `.spy` transformation. |
| [Reference]({{ site.baseurl }}/v3a/reference/) | Look up public signatures, options, results, and exceptions. |
| [Security and Operations]({{ site.baseurl }}/v3a/security-and-operations/) | Prepare automation for failure, security review, and production operation. |
| [Example Gallery]({{ site.baseurl }}/v3a/Example%20Gallery/) | Use and extend safety-labelled operational recipes. |
| [Migration and Releases]({{ site.baseurl }}/v3a/migration-and-releases/) | Update earlier code and review v3.1 changes. |
| [Contributing and Testing](development-and-testing/) | Run the release gate and work on SSHScript itself. |

English is the maintained navigation language for this phase; existing
translated files remain in source but are excluded from the published site and
sidebar. The Example Gallery uses an append-only, one-page-per-case structure
so future scripts can be published without reorganizing established links.

> **Version notice:** SSHScript 3.1.4 is the current Production/Stable release
> on PyPI. Pages marked **Next-release API** describe the updated source
> checkout, including argv, three-value results, unified check, SSH config,
> and compile-only checking. Those changes require the updated source. Begin with
> [Installation and Verification]({{ site.baseurl }}/v3a/getting-started/installation-and-verification/).

Last Updated: 2026-09-26 16:11:31
