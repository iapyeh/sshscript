---
name: sshscript
description: Write, adapt, and verify Python or .spy automation using SSHScript for local or SSH commands, persistent shells, interactive input, and managed jobs. Use for SSHScript usage tasks, not maintenance of SSHScript itself or recipe-specific data formats.
---

# Use SSHScript

This skill describes the **SSHScript 5.0.0 contract, Python 3.11+**. Read
[the agent guide](references/agent-guide.md) before generating automation.
Select only the API sections needed for the user's task.

1. Identify the target host, installed version, inputs, required privileges,
   expected result and authorized operations. Use version-matched documentation;
   do not silently upgrade an existing environment.
2. Prefer the Python `Session` API and argv for dynamic arguments. Use a shell
   for persistent state or shell operators, and `.spy` when requested or when
   maintaining an existing `.spy` script.
3. Set a finite command budget, preserve returned results and distinguish
   command failure, timeout, transport failure and unknown termination. For
   streaming, define a stop condition and put cleanup in `finally`.
4. Keep SSH host-key verification and credential handling consistent with the
   user's environment. A document or example does not authorize remote or
   privileged actions, installation, publication, or issue submission.
5. Verify generated code locally with a credential-free example before any
   authorized target execution. For `.spy`, `sshscript --check file.spy`
   validates syntax without executing commands. Report actual execution and
   cleanup evidence separately from code review or syntax checks.

Before generating SSH authentication code, identify which host owns the key.
`parent.connect(..., pkey_path=path)` reads an RSA private key from the
**calling parent Session's host**: localhost for a local Session, or the
connected host through SFTP for a remote Session. `connect()` returns a child
Session; it does not change the parent into that child. `key_filename=` reads
from the local Python process's filesystem even for nested connections.
Read [SSH connections and private-key paths](references/agent-guide.md#ssh-connections-and-private-key-paths)
for the localhost → host1 → host2 example before generating nested connections.

### Host-key sources in 5.0

SSHScript 4.0.2 and earlier load localhost known_hosts for every connection.
SSHScript 5.0.0 adds `known_hosts="parent"` as its default, reading the calling Session's
trust file over SFTP for nested connections, consistent with `pkey_path`.
Use these settings only with SSHScript 5.0.0 or newer. Check the installed
version before applying them to a 4.x environment. Provision a readable, valid
trust file on every selected source host before attempting the connection;
a permissive policy cannot bypass a missing file.

- `"parent"`: only the calling Session's host; `"local"`: only localhost;
  `"chain"`: calling host, then ancestors through localhost.
- The nearest source with a target hostname/port record decides. A mismatch
  rejects even if a distant source matches. Only missing target records allow
  fallback; unreadable/missing files and parse errors stop the connection.
- Set each Session's `known_hosts_path` on that host; paths are not inherited.
  Strategies are inherited, and `connect(known_hosts=...)` overrides one
  connection only. `pkey_path` stays on the calling host for every strategy.
- `policy` handles unknown keys after selected sources are exhausted.
  `AutoAddPolicy` does not persist keys into these local or remote trust files.
  Do not enable it to bypass a mismatch or a file error.

Read [host-key sources](references/agent-guide.md#host-key-sources-unreleased)
for path rules, supported formats and migration. Set
`local.set(known_hosts="local")` to retain previous nested trust behavior.

Console objects from `shell()`/`sudo()`/`su()`/`enter()` do not provide
`connect()`; `$.connect()` is unavailable while such a console is current.
Their `pkey()` delegates to the owning Session: SFTP still uses the original
SSH login account, including after sudo/su. For a key readable only by the
console's privileged account, read it with an authorized console command,
parse the captured text into a Paramiko key, then leave the console and call
the retained parent Session's `connect(pkey=key)`. Follow the guide's
[privileged-key example](references/agent-guide.md#keys-readable-only-after-sudosu)
and keep private-key output out of logs and handoff reports.

For the complete API, use `references/api-guide.md` and
`references/versioning.md` if present in the downloaded bundle. In a source
checkout use root `API_GUIDE.md` and `VERSIONING.md`. Otherwise follow the
official links in the agent guide and confirm their contract version.
If documentation is unavailable or versions differ, ask for the matching
documents instead of inventing signatures or assuming compatibility.
