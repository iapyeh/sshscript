---
title: "Module API or Dollar Syntax?"
parent: "Getting Started"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 4
permalink: /v3a/getting-started/module-api-or-dollar-syntax/
---

# Module API or Dollar Syntax?

> **Documentation status: Placeholder**

This page will provide a short decision guide. The intended recommendation is
already clear: start new applications, libraries, and testable automation with
the regular Python `Session` API. Adopt Dollar syntax only for standalone
`.spy` scripts where command-shaped notation materially improves readability.

Planned coverage:

- packaging, importing, testing, type tooling, and editor support;
- when concise `.spy` notation is useful;
- how both interfaces share Session, console, result, and transfer behavior;
- mixed projects and migration boundaries; and
- examples of decisions for libraries, deployment tools, and one-off scripts.

For now, begin with the
[Module API Tutorial]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/tutorial/).

Last Updated: 2026-09-17 12:13:56
