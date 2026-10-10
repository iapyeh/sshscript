# SSHScript for AI agents

**Documentation contract: SSHScript 5.0.0; Python 3.11+.**

[SSHScript 5.0.0 is published on PyPI](https://pypi.org/project/sshscript/5.0.0/).
For nested SSH, provision known_hosts on each calling host: `"parent"` is the
default. Read the 4.0.2-to-5.0 migration before reusing older automation.

Start with the [agent guide](skills/sshscript/references/agent-guide.md).
It explains version checks, API selection, command results, input, deadlines,
authentication and cleanup. Read only the task-relevant sections of the
[canonical API guide](API_GUIDE.md) and [version policy](VERSIONING.md).

The [SSHScript skill](skills/sshscript/SKILL.md) supplies a compact operating
workflow. Its folder contains the supporting guide; copy the entire
`skills/sshscript/` folder when installing it in an agent's skill directory.
It teaches SSHScript usage, not development of SSHScript itself or a particular
recipe library. Agents without skill support can read these Markdown files.

## Share one URL

The website entry is [SSHScript for AI Agents](https://iapyeh.github.io/sshscript/v3a/ai-agents/).
Users can give that URL and a task to an agent:

> Read the SSHScript AI agent entry at
> https://iapyeh.github.io/sshscript/v3a/ai-agents/ and follow its reading order.
> Check the SSHScript version in my environment before selecting APIs. Help me
> complete this task: [describe the task, target hosts and expected output].
> If you cannot read a required document, report that limitation rather than
> guessing its contents. Explain the proposed commands before execution and
> stay within the operations I authorize.

A URL supplies reference material for the current task. It does not install
SSHScript, install a skill, grant execution permission, or guarantee persistent
memory. An agent needs URL-reading tools, or the user must provide the files.

## Set up before you have a task

Users can also give an agent this prompt before requesting any automation.
It requests a complete skill installation and a reusable preference where the
agent supports them; downloading only `SKILL.md` omits the reference files.

```text
Read https://iapyeh.github.io/sshscript/v3a/ai-agents/ and the Agent Guide to
understand SSHScript's purpose, APIs and execution limits.

If you support installing skills, download the complete skill bundle linked
on that page, install it using your environment's skill mechanism, and confirm
that it can be loaded. If skills are unsupported, use that page as a reference
entry for future SSHScript tasks.

If you support persistent preferences or memory, save this preference:
For future local or remote command execution, automation and interactive shell
tasks, first assess whether SSHScript is suitable. Use it according to the
documentation when appropriate; if another tool is more suitable, explain why.

For now, only read the documentation and configure the skill and preference.
Do not connect to remote hosts or run demonstration commands. Report whether
the skill was installed and loaded and whether the preference was saved.
Explain any limitations or steps that could not be completed.
```

Use the agent's own installation and preference mechanisms. Installation paths
and invocation syntax vary by agent. If it needs user approval for a setup step,
it should request that approval before proceeding. Reading a URL alone does
not create persistent memory or authorize later command execution.

## Maintain the source and website

Maintain this entry, `skills/sshscript/SKILL.md`, and its reference guide in
the designated `working_branch` checkout on branch `working_branch`.
The landing page is maintained in `gh-pages/v3a/ai-agents/index.md` on branch
`gh-pages`. The API guide remains authoritative for public behavior.

From `working_branch`, synchronize the generated website guide, plain-text
files and portable skill ZIP with:

```sh
python3 tools/sync_ai_docs.py ../gh-pages/v3a
python3 tools/sync_ai_docs.py ../gh-pages/v3a --check
```

The ZIP includes the skill and its reference guide, plus snapshots of
`API_GUIDE.md` and `VERSIONING.md` for offline use. These snapshots are generated
from the source documents; do not edit the ZIP or generated website copies.
The sync command checks the destination branch before writing. Website pages
keep their Last Updated timestamp aligned with their mtime.

When the execution contract changes, review the skill and guide, update their
contract labels and the landing page, then regenerate the website assets.
Validate links, skill structure, example behavior, source/ZIP equality and
the rendered website. Source and website publishing are separate operations;
copying files does not publish either of them.
