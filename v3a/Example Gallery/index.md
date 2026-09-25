---
title: "Example Gallery"
parent: "SSHScript v3.1 Documentation"
nav_order: 7
has_children: true
has_toc: false
---

# Example Gallery

The gallery is a growing collection of complete, reviewable SSHScript cases.
The first three pages provide read-only starting points; future scripts can be
added one case at a time without redesigning the navigation.

| Collection | Initial case | Safety |
| --- | --- | --- |
| [System Administration](system-administration/) | Collect a remote host-health snapshot. | Read-only, SSH required |
| [Networking](networking/) | Test one authorized TCP endpoint from a remote host. | Network connection, SSH required |
| [Accounts](accounts/) | Audit a named account without changing it. | Read-only, identity data |

## An open, append-only structure

New cases should be separate Markdown files under `v3a/Example Gallery/` and
direct children of **Example Gallery**. Keep existing URLs stable and append a
new `nav_order` instead of renumbering or replacing unrelated cases. Group the
catalog here by topic; a title prefix can make the topic obvious, for example:

- `System Administration: Rotate an Application Log`
- `Networking: Verify an HTTPS Certificate`
- `Accounts: Provision a Restricted Service User`

This flat page structure keeps the Just the Docs sidebar within the supported
three navigation levels while allowing any number of cases. If a topic grows
large, this index can add filtered topic tables without moving the case files.

## Required contract for every example

Every contributed case should include:

1. **Goal** — the one operational result the script produces.
2. **Safety label** — for example `read-only`, `writes files`, `privileged`,
   `interactive`, `SFTP`, `network connection`, or `destructive`.
3. **Prerequisites** — SSHScript/Python version, target OS/tools, access, host
   keys, privilege, and test data.
4. **Inputs** — accepted values, validation, defaults, and secret sources.
5. **Effects and failure boundary** — what can change and which partial states
   are possible.
6. **Complete script** — module API first; an optional `.spy` variant can
   follow when Dollar syntax materially improves the case.
7. **Expected result** — exit status and sanitized example output.
8. **Verification, rollback, and cleanup** — how to prove success and recover.
9. **Adaptation notes** — explicit portability and site-policy boundaries.

A runnable example must check nonzero command status, use finite timeouts,
verify host keys by default, preserve argument boundaries, and close every
Session it creates. Examples that need credentials must show a safe source,
never a literal secret.

## Copyable page skeleton

```markdown
---
title: "Topic: Case Name"
parent: "Example Gallery"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: NEXT_NUMBER
---

# Topic: Case Name

| Field | Value |
| --- | --- |
| Safety | read-only / writes / privileged / destructive |
| Interface | Module API / Dollar syntax |
| Target | tested operating systems and required tools |

## Goal

## Prerequisites

## Inputs

## Effects and failure boundary

## Complete script

## Expected result

## Verification, rollback, and cleanup

## Adapt this case

Last Updated: YYYY-MM-DD HH:MM:SS
```

Before publishing a case, run it in an isolated representative environment,
redact the captured output, add it to the catalog above, and run the v3a
documentation validator. Source contributions should also follow
[Contributing and Testing]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/development-and-testing/).

Last Updated: 2026-09-25 16:37:52
