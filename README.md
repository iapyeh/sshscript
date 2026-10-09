---
layout: default
title: "Documentation Repository"
nav_exclude: true
search_exclude: true
---

# Documentation Repository

[![Documentation](https://github.com/iapyeh/sshscript/actions/workflows/docs.yml/badge.svg?branch=gh-pages)](https://github.com/iapyeh/sshscript/actions/workflows/docs.yml)

This `gh-pages` branch contains the source for SSHScript's public
documentation website. It is a documentation and publishing branch, not the
primary source-code branch.

## Published documentation

SSHScript 4.0.2 is the current Production/Stable release. The website also
retains explicitly labelled 3.1 compatibility examples and historical notes:

**[Open the SSHScript documentation](https://iapyeh.github.io/sshscript/v3a/)**

Recommended entry points:

- [Installation and Verification](https://iapyeh.github.io/sshscript/v3a/getting-started/installation-and-verification/)
- [5-Minute Quickstart](https://iapyeh.github.io/sshscript/v3a/getting-started/quickstart/)
- [Module API Tutorial](https://iapyeh.github.io/sshscript/v3a/SSHScript%20v3%20Documents/tutorial/)
- [Session and Console API Reference](https://iapyeh.github.io/sshscript/v3a/reference/session-and-console-api/)
- [Production Checklist](https://iapyeh.github.io/sshscript/v3a/security-and-operations/failure-model-and-production-checklist/)
- [Current release on PyPI](https://pypi.org/project/sshscript/)

## About SSHScript

SSHScript is a Python automation library and `.spy` script runner for
executing commands locally or over SSH. The regular Python `Session` API is
the primary interface in 4.0. Dollar syntax is an optional shorthand for
concise operational scripts.

## Branch layout

| Path | Purpose |
| --- | --- |
| `v3a/` | Actively maintained SSHScript website; stable legacy URL |
| `v1/`, `v2/`, `v3/` | Historical documentation; excluded from current navigation and search |
| `_config.yml` | GitHub Pages and Just the Docs configuration |
| `tools/check_docs.py` | Source-level documentation validation |
| `info.json` | Published stable-version information |

New documentation work belongs under `v3a/` unless a change explicitly
targets branch-level publishing files such as this README or `_config.yml`.

## Documentation policy

- Present the regular Python `Session` API first.
- Treat Dollar syntax as an optional `.spy` add-on.
- Maintain English as the published documentation language for the current
  phase.
- Keep examples generic and safe to publish.
- Keep unfinished placeholder pages in source and link them from their
  category index, but exclude them from sidebar navigation and search.
- Do not duplicate the sidebar with a manually maintained child-page table of
  contents.
- End each maintained v3a Markdown document with
  `Last Updated: YYYY-MM-DD HH:MM:SS` and match its filesystem mtime.

## Sidebar navigation

The site uses
[Just the Docs](https://just-the-docs.github.io/just-the-docs/) navigation.
The front matter `title` must equal the document's first H1. Child pages must
use the exact parent title; third-level pages also declare `grand_parent`.

```yaml
---
title: "Session and Console API Reference"
parent: "Reference"
grand_parent: "SSHScript Documentation"
nav_order: 1
---
```

A category index declares `has_children: true`. Keep `nav_order` values
stable and unique among visible siblings.

Additional project-specific sidebar rules are maintained in
[`v3a/rules.txt`](https://github.com/iapyeh/sshscript/blob/gh-pages/v3a/rules.txt).

## Validation before publishing

Run the repository validator:

```sh
python3 tools/check_docs.py
python3 tools/check_docs.py --check-mtime
git diff --check
# After Jekyll generates _site:
python3 tools/check_built_docs.py _site
```

The documentation workflow repeats source validation and performs a Jekyll
build for every pull request and push. It checks front matter, title/H1
equality, navigation relationships, internal links, placeholder visibility,
release-truth guardrails, and `Last Updated` format. The local
`--check-mtime` mode additionally enforces the filesystem timestamp rule;
CI omits it because Git checkouts do not preserve source mtimes.
The post-build check verifies rendered pages, sidebar entries, search records,
local assets, links, and anchors. The current `v3a` scope explicitly enables navigation and search, overriding
the historical `v3` prefix under Jekyll 4 while remaining compatible with
GitHub Pages (Jekyll 3).

Before publishing, also review examples for current 4.0 behavior, credentials,
internal infrastructure details, and unsafe defaults. Changes pushed to
`gh-pages` become public through GitHub Pages.

## Security

Never commit passwords, private keys, tokens, real host inventories, internal
network addresses, or captured secrets to this branch. Use neutral example
accounts and reserved example domains.

## Source and license

SSHScript source code, releases, and issue tracking are available in the
[iapyeh/sshscript repository](https://github.com/iapyeh/sshscript).
SSHScript is released under the MIT License.

Last Updated: 2026-10-09 10:41:00
