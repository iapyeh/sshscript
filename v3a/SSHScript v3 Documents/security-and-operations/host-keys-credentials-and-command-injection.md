---
title: "Host Keys, Credentials, and Command Injection"
parent: "Security and Operations"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
permalink: /v3a/security-and-operations/host-keys-credentials-and-command-injection/
---

# Host Keys, Credentials, and Command Injection

A successful login is not enough to make an SSH automation trustworthy. The
client must authenticate the server, the server must authenticate the intended
account, and every value that reaches a command must retain its intended
argument boundary.

## Verify the server before sending credentials

`Session.connect()` loads the account's system host-key database and rejects an
unknown or changed key by default. Prepare `known_hosts` before the automation
runs:

1. Obtain the server fingerprint through an independent trusted channel, such
   as an administrator-controlled console or configuration inventory.
2. Compare it with the key presented for the exact hostname and port used by
   the automation.
3. Install the verified key in the automation account's `known_hosts` file.
4. Test that the expected key succeeds and a deliberately different key fails.

`ssh-keyscan` can collect a key, but the scan itself does not authenticate that
key. Compare its fingerprint with an independently obtained fingerprint before
installing it.

```python
from sshscript import Session


local = Session()
try:
    with local.connect(
        "ops@example.net",
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
    ) as remote:
        remote.exec_command("hostname", shell=False, timeout=20)
except BaseException as primary:
    if not local.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    local.close(strict=True)
```

Do not respond to an unknown-host error by applying Paramiko's
`AutoAddPolicy` to routine production connections. A permissive policy can be
appropriate only in a controlled bootstrap process that authenticates the key
by another trusted mechanism and persists the verified result. Treat a changed
key as a security event until rotation or compromise has been independently
resolved.

Each hop has its own trust boundary. A nested connection through a bastion must
verify the destination key as well as the bastion key. A `proxyCommand` is a
local process with the privileges and environment of the caller; allow only a
reviewed, fixed command rather than constructing it from untrusted text.

## Choose a credential source

Prefer credentials that do not have to be embedded in the program:

1. a managed SSH agent or short-lived SSH certificate;
2. a protected key file selected with `key_filename=`;
3. a secret obtained at runtime from an approved secret manager; or
4. interactive input with `getpass.getpass()` when unattended execution is not
   required.

```python
from getpass import getpass
from sshscript import Session


password = getpass("SSH password: ")
local = Session()
try:
    with local.connect(
        "example.net",
        username="ops",
        password=password,
        allow_agent=False,
        look_for_keys=False,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
    ) as remote:
        remote.exec_command("id", shell=False, timeout=20)
except BaseException as primary:
    password = None
    if not local.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    password = None
    local.close(strict=True)
```

Setting the Python variable to `None` does not guarantee that every memory copy
has been erased. It merely shortens the obvious lifetime. For unattended use,
prefer an agent, certificate, or secret-manager integration and apply the least
privilege possible to both the SSH account and any `sudoers` rule.

`pkey_path=` is a compatibility helper that loads an RSA key from the parent
Session's host. For normal local authentication, Paramiko's `key_filename=` and
agent support are clearer and also avoid transferring private-key contents into
application code.

## Keep secrets out of observable surfaces

Never place a password, token, or private key in:

- source code or a committed configuration file;
- a command-line argument or generated command string;
- an exception message, assertion message, or correlation identifier;
- routine stdout, stderr, or debug logging; or
- a public issue, traceback, terminal capture, or CI artifact.

The CLI's ordinary runtime error record omits exception payloads, but
`--traceback` can reveal source lines, paths, commands, and data. Syntax-error
diagnostics may show the failing source line even without `--traceback`. Use
full diagnostics only in a controlled environment and redact them before
sharing.

For an interactive password prompt, use a narrowly matched prompt and a finite
timeout. Do not print the password or the complete interaction transcript. See
[Interactive Programs with `Session.enter()`]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/Advanced/enter/) for the
protocol and failure cases.

## Preserve argument boundaries

`Session.exec_command()` accepts one non-empty command string. When a command
does not need shell syntax, build an argument list in Python, convert it with
`shlex.join()`, and request `shell=False`:

```python
import shlex


arguments = ["install", "-m", "0644", source_path, destination_path]
command = shlex.join(arguments)
stdout, stderr = remote.exec_command(command, shell=False, timeout=30)

if remote.exitcode != 0:
    raise RuntimeError(
        f"install failed with exit status {remote.exitcode}"
    )
```

Do not pass the list itself; v3.1 raises `TypeError`. `shlex.join()` preserves
argument boundaries, including spaces and metacharacters. It does not decide
whether an executable, flag, account name, path, or operation is authorized.
Validate those values against the application's policy as well.

On localhost, `shell=False` launches the parsed argument vector without a
shell. Over SSH, SSHScript re-quotes the vector and sends `exec ...` through
the server's command shell. Operators are passed as ordinary arguments rather
than interpreted as user shell syntax, but a server-side shell still
participates.

## When a shell is required

Pipelines, redirection, expansion, assignments, and shell builtins require a
shell. Keep the program structure fixed and quote each data value separately:

```python
import shlex


safe_since = shlex.quote(since)
safe_text = shlex.quote(search_text)
command = (
    f"journalctl --since {safe_since} "
    f"| grep -F -- {safe_text}"
)
stdout, stderr = remote.exec_command(command, shell=True, timeout=30)
```

Avoid accepting an entire command from a web request, message, inventory field,
or environment variable. Quoting a value prevents it from becoming shell
syntax; it does not make an arbitrary command safe. Prefer a small allowlist of
operations and map each operation to a fixed executable and fixed flag set.

Automatic shell detection is convenient for constant commands, but security-
sensitive code should state `shell=False`, `shell=True`, or `shell="bash"`
explicitly. Review the portability and trust implications of a named shell on
every target platform.

## Paths, transfers, and privilege

`upload()` and `download()` use SFTP, so their paths are not interpolated into
a command. They still require path authorization: normalize local roots,
constrain remote destinations, and decide whether overwriting is allowed.

SFTP always uses the identity that opened the SSH connection. Entering
`sudo()` or `su()` changes command identity, not SFTP identity. For a privileged
destination, upload to a controlled staging path, verify the content, then use
a narrowly scoped privileged command to install it. Remove the staged copy in a
`finally` block.

## Security review checklist

- [ ] The exact host and port are known before connection.
- [ ] Every host fingerprint is verified independently and installed in
      `known_hosts`.
- [ ] Unknown and changed keys fail closed.
- [ ] Credentials come from an agent, protected key, certificate, or approved
      runtime secret source.
- [ ] Commands and diagnostics never contain secrets.
- [ ] Dynamic arguments use `shlex.join()` with `shell=False` where possible.
- [ ] Shell-mode data values are individually quoted and semantically
      validated.
- [ ] Executables, operations, paths, and privilege transitions are allowlisted.
- [ ] Logs contain sanitized operation names and result types, not raw payloads.
- [ ] Site-specific host-key rotation, PAM, `sudoers`, and incident procedures
      have been tested.

Continue with [Timeouts, Retries, and Cleanup](../timeouts-retries-and-cleanup/)
and the [Failure Model and Production Checklist](../failure-model-and-production-checklist/).

Last Updated: 2026-09-25 16:37:52
