---
title: "Accounts"
parent: "Example Gallery"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
---

# Accounts

This collection starts with a read-only account audit. Add future account cases
as separate Gallery pages; state the executing identity, target identity,
privilege, audit record, rollback, and secret-handling contract for each one.

## Case: audit a named account

| Field | Value |
| --- | --- |
| Safety | Read-only; output contains identity and group data |
| Interface | Module API |
| Target | POSIX SSH host with `id` |
| Privilege | Ordinary account able to query the named account |
| Effects | Opens one verified SSH connection and reads account metadata |

### Goal

Confirm that a named account exists and capture the identity record returned by
`id` with argument-preserving execution and without modifying the account
database. Over SSH, the server's command shell still participates, but the
quoted account value is not interpreted as shell syntax.

### Prerequisites

- SSHScript 3.1.4 and Python 3.11 or newer on the runner;
- the target's verified key in `known_hosts`;
- authorization to view account and group membership; and
- a non-secret account name supplied as input.

### Complete script

Save as `account_audit.py`:

```python
#!/usr/bin/env python3
import argparse
import json
import re
import shlex

from sshscript import Session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ssh_target", help="user@host or host")
    parser.add_argument("account")
    args = parser.parse_args()

    if not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_.-]*[$]?",
        args.account,
    ):
        parser.error("account has an unsupported portable name")

    command = shlex.join(["id", args.account])
    local = Session()
    try:
        with local.connect(
            args.ssh_target,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        ) as remote:
            stdout, stderr = remote.exec_command(
                command,
                shell=False,
                timeout=20,
            )
            result = {
                "account": args.account,
                "exitcode": remote.exitcode,
                "identity": str(stdout).strip(),
            }
            diagnostic = str(stderr).strip()
    except BaseException as primary:
        if not local.close():
            primary.add_note("SSHScript cleanup also failed")
        raise
    else:
        local.close(strict=True)

    if result["exitcode"] != 0:
        raise SystemExit(
            f"account lookup failed with exit status {result['exitcode']}"
        )
    if diagnostic:
        raise SystemExit("account lookup produced unexpected stderr")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

Run it for an authorized account:

```sh
python3 account_audit.py ops@example.net app-service
```

`shlex.join()` plus `shell=False` keeps the account name in one argument. The
application must still decide which account names the caller is authorized to
query.

### Expected result

A successful run exits with status 0 and prints a JSON object similar to:

```json
{
  "account": "app-service",
  "exitcode": 0,
  "identity": "uid=1001(app-service) gid=1001(app-service) groups=1001(app-service)"
}
```

Treat this output as potentially sensitive inventory data. Store and transmit
it according to the target organization's access and retention policy.

### Verification and cleanup

The command is read-only and creates no files, so rollback is not required.
Verify the identity through the system's authoritative account source if the
result is used for an access decision. The remote child and root Session are
closed even when the command fails.

### Adapt this case

Account creation, key rotation, group changes, locking, and deletion are
state-changing operations. Publish each as a separate case with an allowlisted
target, least-privilege rule, before/after audit evidence, idempotent behavior,
secret handling, rollback, and a test on the site's actual directory/PAM
stack.

Last Updated: 2026-09-25 16:37:52
