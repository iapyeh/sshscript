# SSHScript Agent Guide

**Documentation contract: SSHScript 4.0.2; Python 3.11+.**

SSHScript runs commands locally and over SSH with a Python `Session` API.
Optional `.spy` dollar syntax exposes the same execution model. Use it when
Python data processing and scoped local/remote command execution fit the task.
This guide concerns using SSHScript, not modifying its repository or defining
a recipe's data schema.

## Read in this order

1. Confirm the installed version and execution environment below.
2. Run the credential-free quickstart, if local execution is authorized.
3. Select the execution mode and read its relevant API section.
4. Before remote execution, review host keys, credentials and connection budgets.
5. Retain results and report validation and cleanup limits.

The public [canonical API guide](https://iapyeh.github.io/sshscript/v3a/recommended-api/)
owns API semantics. The [version policy and migration guide](https://iapyeh.github.io/sshscript/v3a/migration-and-releases/version-policy/)
explains compatibility. Website URLs follow maintained documentation: inspect
their version labels rather than assuming they are immutable references.
For a source checkout, prefer its root `API_GUIDE.md` and `VERSIONING.md`.
The downloadable skill ZIP includes these documents as
`references/api-guide.md` and `references/versioning.md` snapshots. Relative
links inside those snapshots may refer to the original repository layout;
use the website or matching checkout for supplementary files.

## Identify the environment

Use the interpreter that will execute the automation:

```sh
python3 -c 'import sys, platform, importlib.metadata as m, sshscript; print(sys.executable); print(sys.version); print(platform.platform()); print("import:", sshscript.__version__); print("distribution:", m.version("sshscript")); print("module:", sshscript.__file__)'
sshscript --version
```

A metadata lookup can fail in an uninstalled source checkout. In that case,
record the import version, source path, commit and dirty state. If CLI and
import versions differ, resolve the interpreter/environment mismatch first.
Do not assume the website version matches the user's installed package.

For a new environment, when installation is authorized:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install 'sshscript==4.0.2'
```

Pin transitive dependencies in the application's lock file for repeatable
deployment. Python 3.11+ is required. Consult the project's test reports for
actual platform evidence; availability of a Python package is not proof of
native SSH, PAM or sudo behavior on every host.

For 3.1.5, use its version-labelled documentation or plan an explicitly
authorized migration. In particular, 3.1.5 persistent-console calls return
two live buffers; 4.0 completed-console calls return `CommandResult` snapshots.
Do not generate 4.0 settings or managed-job APIs against an older installation.

## Credential-free quickstart

This example uses the same Python interpreter for the child process. It sends
exact stdin, applies a five-second total command budget and retains the result:

```python
from contextlib import closing
import sys
from sshscript import Session

with closing(Session()) as local:
    result = local.exec_command(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
        input="sshscript is ready\n",
        command_timeout=5,
        check=True,
    )
print(result.stdout, end="")
print(f"exit code: {result.exitcode}")
```

Expected output:

```text
sshscript is ready
exit code: 0
```

`closing` calls `close()` but does not inspect its boolean return. When cleanup
failure matters, inspect `close_errors` or use `close(strict=True)` after leaving
owned contexts; preserve an already-raised execution exception when reporting
cleanup problems. A plain root `with Session()` activates a reusable Session
and does not close it.

## Choose the execution boundary

| Task | Choice | Read next |
| --- | --- | --- |
| One finite command with dynamic arguments | `session.exec_command(argv, check=True, command_timeout=30)` | [One command, one result](https://iapyeh.github.io/sshscript/v3a/recommended-api/#one-command-one-retained-result-40-compatible-with-315) |
| Pipeline or shell expansion | Command string with explicit `shell=True`; quote dynamic values | [Direct versus shell execution](https://iapyeh.github.io/sshscript/v3a/concepts/direct-execution-vs-shell-execution/) |
| SSH command | `with local.connect(...) as remote:` followed by `remote.exec_command(...)` | [First SSH connection](https://iapyeh.github.io/sshscript/v3a/getting-started/first-ssh-connection/) |
| Preserve cwd, environment or privilege context | `shell()` or authenticated `su()`/`sudo()`; check each command | [Completed console results](https://iapyeh.github.io/sshscript/v3a/recommended-api/#unreleased-command-results-and-long-running-programs) |
| Observe output before a command ends | `Session.start(argv, timeout=30)` or `console.start(quoted_string, timeout=30)` | [Managed jobs](https://iapyeh.github.io/sshscript/v3a/recommended-api/#unreleased-settings-and-managed-jobs) and [console jobs](https://iapyeh.github.io/sshscript/v3a/recommended-api/#unreleased-foreground-jobs-inside-shell-sudo-and-su) |
| Answer an interactive program | `enter()`, `expect()`, `input()` or `send()` | [Exact stdin and replies](https://iapyeh.github.io/sshscript/v3a/recommended-api/#unreleased-exact-stdin-and-explicit-interactive-replies) |
| Maintain compact `.spy` automation | Single `$` command syntax; `$(argv, check=True)` for dynamic arguments | [Dollar syntax tutorial](https://iapyeh.github.io/sshscript/v3a/tutorials/dollar-syntax/) |

An argv list is **one command**, not a batch. Local argv executes directly;
remote argv is quoted for a POSIX login shell. Shell operators inside argv
are literal data. Console commands accept strings; quote dynamic arguments
with `shlex.join()`. Do not interpolate untrusted values into shell syntax.

## SSH connections and private-key paths

Before choosing an authentication parameter, identify the host containing the
private-key file. `parent.connect(target, pkey_path=path)` calls
`parent.pkey(path)` to load an RSA private key from the **calling parent
Session's host**:

| Calling Session | Where `pkey_path` is read |
| --- | --- |
| Local Session | Localhost, where the Python process runs |
| Session connected to host1 | Host1, through that Session's SFTP connection |

`connect()` returns a new child Session. The parent keeps its original host;
calling `local.connect(...)` again still reads `pkey_path` on localhost.
For a nested connection, call `host1.connect(...)` to read it on host1.

The following example requires authorized SSH access, verified host keys and
RSA key files at the indicated locations; it is not a local smoke test:

```py
from contextlib import closing
from sshscript import Session

with closing(Session()) as local:
    with local.connect(
        "ops@host1.example.net",
        pkey_path="/home/localuser/.ssh/host1_rsa",  # File on localhost.
        timeout=10, banner_timeout=10, auth_timeout=10,
    ) as host1:
        with host1.connect(
            "deploy@host2.example.net",
            pkey_path="/home/ops/.ssh/host2_rsa",  # File on host1, read via SFTP.
            timeout=10, banner_timeout=10, auth_timeout=10,
        ) as host2:
            result = host2.exec_command(["hostname"], check=True, command_timeout=10)
            print(result.stdout)
```

In `.spy`, nested `with $.connect(...)` scopes select the current parent
Session, so an inner `pkey_path` is read from the outer scope's connected host.
`key_filename=` has different semantics: Paramiko reads it from the local
Python process's filesystem, including for nested SSH connections. It supports
key formats beyond RSA. To use an encrypted RSA key with `pkey_path` semantics,
load it explicitly with `parent.pkey(path, password=key_passphrase)` and pass
the returned object as `pkey=`; do not supply both `pkey` and `pkey_path`.

### Host-key sources (unreleased)

This section describes the development checkout, not published SSHScript 4.0.2.
`known_hosts` selects the host-key trust source independently of `policy`:

| Value | Sources, in order |
| --- | --- |
| `"parent"` (new default) | Only the calling Session's host |
| `"local"` | Only the root localhost Session |
| `"chain"` | Calling Session, then each ancestor through localhost |

For localhost → host1 → host2 → host3, `host2.connect("host3",
known_hosts="chain")` consults host2, host1, then localhost. The nearest source
with a record for the resolved target hostname and port is authoritative.
A matching key is accepted; a changed key is rejected even if a more distant
source matches. Only absence of a target record permits continuing the chain.
Different key algorithms do not permit falling back to another source.

Each source reads its own `known_hosts_path`, or `~/.ssh/known_hosts` if unset.
Remote files are read over SFTP as that Session's original SSH login account;
SSH handshakes, user authentication and host-key verification still run in the
local Python process. Neither sudo/su nor a nested connection changes the SFTP
account. Remote `~/` paths refer to the login account's SFTP home; `~user` paths
are unsupported. Relative remote paths use the SFTP working directory.

```py
local.set(known_hosts="chain")
# After connecting to host1 and host2:
host1.set(known_hosts_path="/home/ops/.ssh/known_hosts")
host2.set(known_hosts_path="/etc/ssh/ssh_known_hosts")
with host2.connect("deploy@host3", pkey_path="/home/ops/.ssh/host3_rsa") as host3:
    result = host3.exec_command(["hostname"], check=True, command_timeout=10)
```

The strategy is inherited by future child Sessions; the path is host-specific
and is **not inherited**. `known_hosts_path=None` restores the standard path.
A `connect(known_hosts=...)` override affects only that connection; it does not
change the parent setting or the child's inherited strategy. `set()`, `get()`
and matching properties expose both settings. `known_hosts_path` accepts text
paths and `PathLike[str]`; it is a Session setting, not a `connect()` keyword.

`pkey_path` always reads only from the calling Session's host, including with
`known_hosts="chain"`; private keys are never searched through ancestors.

An absent trust file, permission failure, read failure, invalid UTF-8 or invalid
entry raises an error; no distant source or permissive policy bypasses it.
Empty files, comments, plain host-key entries (including comma-separated names)
and hashed hostnames are supported. OpenSSH markers such as `@cert-authority`
and `@revoked`, wildcard/negated host patterns and unsupported key types raise
an error rather than being silently ignored. A source file is fully parsed
before its records are used. Nonstandard ports use `[hostname]:port` records.

When every selected source lacks the target, `policy` handles the unknown key.
`AutoAddPolicy` accepts it into the new client's memory only; these trust files
are read-only and are not automatically updated locally or remotely.

**Migration:** published 4.0.2 always loads localhost host keys. The new default
`"parent"` makes nested host-key sources consistent with `pkey_path`. To retain
the previous behavior, set `local.set(known_hosts="local")` before connecting.
All strategies require a readable, valid file, including the default localhost
path. Unlike published 4.0.2, a missing local file is an error; create an empty
file if the configured missing-key policy should handle unknown hosts.

### Keys readable only after sudo/su

SFTP uses the original SSH login account. `sudo()` and `su()` change the
console command identity, not SFTP permissions. Calling `$.pkey()` inside
either scope still delegates to the owning Session, so a root-only key can
fail with a permission error even when console commands run as root.

Console objects yielded by `shell()`/`sudo()`/`su()`/`enter()` do not provide
`connect()`. In those `.spy` scopes, `$.connect()` therefore fails. A retained
Python Session's `connect()` is not blocked by an active console, but it uses
the original SSH transport and does not inherit sudo/su identity. Prefer
leaving the console before opening the child connection.

When authorized to use a privileged key, read it as a console command, check
that the command succeeded, parse its captured output, then pass the resulting
Paramiko key as `pkey=`. This avoids an SFTP read during `connect()`.
The `.spy` example below requires authorized sudo and SSH access, verified
host keys, and an RSA key that authenticates `deploy` on host2:

```spy
from io import StringIO
import paramiko

with $.connect("ops@host1.example.net", timeout=10,
               banner_timeout=10, auth_timeout=10) as host1:
    with $.sudo():
        key_result = $("cat /root/.ssh/id_rsa", check=True, command_timeout=10)
        key = paramiko.RSAKey.from_private_key(StringIO(key_result.stdout))

    with host1.connect("deploy@host2.example.net", pkey=key,
                       timeout=10, banner_timeout=10, auth_timeout=10):
        $hostname
```

After a successful `$cat /root/.ssh/id_rsa`, `StringIO($.stdout)` can also
supply the key text; check `$.exitcode` before parsing and capture stdout
before another command replaces it. The saved result above retains the
specific command's output. In Python, use
`with host1.sudo() as root:` and
`key_result = root("cat /root/.ssh/id_rsa", check=True, command_timeout=10)`.
The same approach works with an authorized `su()` scope. For an encrypted
RSA key, add `password=key_passphrase` to `from_private_key()`; use the
appropriate Paramiko key class for other key formats.

Private-key text enters console buffers and the captured result. Configure
output logging/display so it does not expose this command's output before
reading the key; do not print, persist, or include that output in diagnostics
or handoff reports. Console privilege only permits reading the file; host2
authentication is determined by the supplied key and target username.

## Retain evidence and handle failure

Save each returned result; read `stdout`, `stderr`, `exitcode`, `host`,
`duration` and `command`. Three-value unpacking is exactly
`stdout, stderr, exitcode`. `host` snapshots the Session target and is `None`
locally; it does not query the OS hostname. Console output properties are live
buffers and should not replace saved completed results.

`check=True` raises `subprocess.CalledProcessError` for a nonzero command exit
and preserves the result on `error.result`. If nonzero exit is expected, use
`check=False` for that command and interpret its status explicitly.
Connection/transport errors and timeouts remain failures, not fabricated exit
codes or empty successful records.

Use `exec_command(command_timeout=...)` for a total command deadline on local
and SSH backends. It selects managed execution and returns `JobResult`, a
`CommandResult` subclass. Legacy `timeout=` has backend-specific semantics;
do not combine it with `command_timeout`. Set connection `timeout`,
`banner_timeout` and `auth_timeout` separately for SSH setup.

On `CommandTimeoutError`, retain partial `error.result`. Managed output is
bounded; inspect `stdout_truncated` and `stderr_truncated` before treating it
as complete. PTYs can merge stderr into stdout. Streaming yields chunks,
not necessarily complete lines; slow consumers can raise `BufferError`.

## Streaming and cleanup

Prefer a finite command or bounded capture with a deadline. For streaming,
use a job context, a finite `timeout`, an explicit stop condition and
`job.stop()` in `finally`. `timeout=None` removes the total deadline and needs
an independent stopping mechanism. Checking time only when output arrives
cannot bound a silent process.

Read `stop_reason` and `termination_status` on the completed job result.
A stop request or SSH channel closure does not prove that the remote process
or detached descendants stopped. Reconcile `termination_status="unknown"`
with a separate host/process check within the user's authorization.

A persistent console supports one foreground job at a time. Use its job's
stream/wait/stop methods while active; other console operations are rejected.
Console-job user operations belong to the creating thread. Failed shell
recovery disables the channel; do not clear that failure and continue.
Leave shell/su/sudo/enter contexts before closing their owning Session.

## Input and authentication

`input=data` sends exact stdin: strings use UTF-8, bytes stay bytes, and no
newline is added. Supplied data, including empty input, is followed by EOF.
Use `input="answer\n"` when a line is required; `input=""` for explicit EOF.
`input=None` retains backend-specific no-payload behavior.

Inside an interactive `enter()` scope, `program.input(answer)` appends one
newline and waits for readiness, exit or silence; `program.send(text)` writes
exact text. `input("answer\n")` therefore sends two newlines. Neither a prompt
nor temporary silence proves successful authentication or command completion.

Keep verified known-host keys and the default rejection of unknown keys unless
the user explicitly selects another trust policy. Do not silently enable
`AutoAddPolicy`. Source credentials from the user's configured mechanism or
`getpass`, not hardcoded examples or logs; verbose output can expose secrets.

Prefer authenticated `su()`/`sudo()` scopes for privilege transitions. Their
entry handshake must succeed before running commands. Entry failure belongs
outside the `with` body; passwords are sent at most once, not automatically
retried. Custom templates require `{auth_command}` or
`{auth_command_quoted}` without extra surrounding quotes. Consult the
[authenticated-console contract](https://iapyeh.github.io/sshscript/v3a/recommended-api/#unreleased-authenticated-susudo-consoles)
for recovery and native-system limitations.

## Verify and hand off

For `.spy`, syntax-check with `sshscript --check file.spy` before authorized
execution with `sshscript file.spy`. Syntax validation does not test target
commands. For Python, run a credential-free smoke example and focused tests
for parsing and failure handling. Remote SSH and native su/sudo validation are
separate evidence; do not claim them from a local success.

Report the interpreter, package version (and source commit/dirty state when
applicable), target, relevant non-secret inputs, exact command, retained result,
timeout/transport errors, truncation and cleanup/termination status. Verify the
application's expected outcome separately: exit code zero is not proof of a
successful deployment. Keep observed facts separate from inference and unknowns.

Use the [Example Gallery](https://iapyeh.github.io/sshscript/v3a/Example%20Gallery/)
for operational examples and the [support policy](https://github.com/iapyeh/sshscript/blob/release/SUPPORT.md)
for reporting issues. Recipe-specific schemas and vault updates belong to that
recipe's own documentation. Reading this guide does not authorize executing
examples or submitting a public report.
