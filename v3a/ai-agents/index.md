---
title: "SSHScript for AI Agents"
parent: "SSHScript Documentation"
nav_order: 10
has_children: true
has_toc: false
permalink: /v3a/ai-agents/
---

# SSHScript for AI Agents

Give your agent this page and a task. SSHScript lets it write Python automation
for local and SSH commands, retain command output and status, and manage
persistent shells and streaming jobs. Start with the regular Python `Session`
API; optional `.spy` syntax uses the same execution contract.

**Documentation contract: SSHScript 4.0.2; Python 3.11+.** Check the installed
version before selecting APIs. Older 3.1.5 console behavior differs from 4.0.
The `/v3a/` URL is the maintained documentation location, not a package-version
identifier. Reading this page does not install anything or authorize execution.

## Copy this prompt

Replace the task description and give the following to an agent that can read
web pages:

```text
Read https://iapyeh.github.io/sshscript/v3a/ai-agents/ and follow its reading
order. Confirm the SSHScript version in my environment and use matching
documentation. Help me complete this task:
[Describe the task, target hosts, inputs and expected output.]

Read the agent guide and only the API sections relevant to my task. Explain
the proposed commands before execution and stay within the operations I
authorize. Preserve command results and report timeout, transport and cleanup
failures separately. If you cannot read a required document, tell me instead
of guessing its contents.
```

An agent uses these documents as reference material in the current task;
permanent learning or memory depends on that agent's capabilities. If it
cannot fetch URLs, provide the plain-text guide or downloaded bundle instead.

## Start here: reading order

1. Read the [SSHScript Agent Guide]({{ site.baseurl }}/v3a/ai-agents/guide/)
   for version identification and a credential-free quickstart.
2. Consult the [version policy]({{ site.baseurl }}/v3a/migration-and-releases/version-policy/)
   if the installation differs from this guide's contract. Resolve mismatches
   before generating or running version-dependent code.
3. Choose the relevant execution mode in the guide, then read the
   [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/).
4. For remote tasks, review
   [host keys, credentials and command injection]({{ site.baseurl }}/v3a/security-and-operations/host-keys-credentials-and-command-injection/)
   and [timeouts and cleanup]({{ site.baseurl }}/v3a/security-and-operations/timeouts-retries-and-cleanup/).
5. Use the [Example Gallery]({{ site.baseurl }}/v3a/Example%20Gallery/)
   for task examples. Check each example's prerequisites and validation limits.

The guide and API references are ordinary text with direct links; navigating
this material does not require JavaScript, a search service, or skill support.

## Optional portable skill

<!-- Static download assets are verified by tools/check_built_docs.py. -->

Download <a href="{{ site.baseurl }}/v3a/ai-agents/downloads/sshscript-skill.zip">the SSHScript skill ZIP</a>.
It contains a `sshscript/` folder with `SKILL.md`, the agent guide, and API and
version-policy snapshots for the documented contract. Keep the whole folder
together. For Codex, place it under your configured skills directory, commonly
`~/.codex/skills/sshscript/`, then invoke `$sshscript`. Other agents should use
their own skill installation mechanism; a `SKILL.md` file alone does not imply
universal support or automatic installation.

For agents without skill support, read the
<a href="{{ site.baseurl }}/v3a/ai-agents/downloads/agent-guide.txt">plain-text agent guide</a>
and <a href="{{ site.baseurl }}/v3a/ai-agents/downloads/SKILL.txt">plain-text skill instructions</a>,
or supply the bundle's Markdown files as task context. Neither reading a skill
nor downloading it executes SSH commands.

## Source, versions and feedback

The repository maintains the skill and guide; the web guide and downloads are
generated from those sources. The API guide owns public behavior. Pin the
tested package version and retain artifact or source-commit identity when
handing off automation. This maintained URL and ZIP may change when the
documentation contract changes; retain the downloaded bundle for reproducibility.

SSHScript API problems belong to the SSHScript project. Recipe-specific
collection logic, schemas and vault updates belong to their recipe project.
Follow the [support policy](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)
for feedback; public submission requires the user's authorization.

Last Updated: 2026-10-09 16:37:55
