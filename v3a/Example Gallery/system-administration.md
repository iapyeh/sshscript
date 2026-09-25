---
title: "System Administration"
parent: "Example Gallery"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
---

# System Administration

This collection starts with a read-only host-health snapshot. Add future system
administration cases as separate Gallery pages so each script can state its own
privilege, side effects, rollback, and verification contract.

## Case: collect a host-health snapshot

| Field | Value |
| --- | --- |
| Safety | Read-only |
| Interface | Module API |
| Target | POSIX SSH host with `uname`, `uptime`, and `df` |
| Privilege | Ordinary account |
| Effects | Opens one verified SSH connection and reads system state |

### Goal

Run three independent checks on one host and emit a JSON report. Each command
uses argument-preserving execution, a finite I/O timeout, and explicit status
handling.

### Prerequisites

- SSHScript 3.1.4 and Python 3.11 or newer on the runner;
- a target account authenticated by an agent or configured key;
- the target's independently verified key in `known_hosts`; and
- permission to collect the selected operational data.

### Complete script

Save as `host_health.py`:

```python
#!/usr/bin/env python3
import argparse
import json
import shlex

from sshscript import Session


CHECKS = {
    "kernel": ["uname", "-sr"],
    "uptime": ["uptime"],
    "root_filesystem": ["df", "-P", "/"],
}


def collect(remote):
    report = {}
    for name, arguments in CHECKS.items():
        stdout, stderr = remote.exec_command(
            shlex.join(arguments),
            shell=False,
            timeout=20,
        )
        status = remote.exitcode
        if status != 0:
            raise RuntimeError(
                f"{name} failed with exit status {status}"
            )
        report[name] = str(stdout).rstrip("\n")
        if str(stderr):
            report[f"{name}_stderr"] = str(stderr).rstrip("\n")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ssh_target", help="user@host or host")
    args = parser.parse_args()

    local = Session()
    try:
        with local.connect(
            args.ssh_target,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        ) as remote:
            report = collect(remote)
    except BaseException as primary:
        if not local.close():
            primary.add_note("SSHScript cleanup also failed")
        raise
    else:
        local.close(strict=True)

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

Run it with the same environment in which SSHScript was verified:

```sh
python3 host_health.py ops@example.net
```

### Expected result

The program exits with status 0 and emits one JSON object. Values depend on the
host; a shortened example is:

```json
{
  "kernel": "Linux 6.x",
  "root_filesystem": "Filesystem ...",
  "uptime": "16:20:00 up ..."
}
```

A failed check raises with only the check name and exit status. The example
does not print stderr on failure because diagnostics can contain sensitive
paths or system data. Add reviewed, redacted logging for your environment.

### Verification and cleanup

The case changes no remote state, so rollback is not required. Confirm that all
three keys are present and that the output matches the target host. Both the
remote child and root Session are closed; cleanup failure cannot silently turn
the run into success.

### Adapt this case

Add checks only when they remain read-only and are available on every declared
target platform. Give each command its own stable name and status policy. For a
state-changing operation, create a separate Gallery page with preconditions,
backup, idempotency, verification, rollback, and partial-failure behavior.

Last Updated: 2026-09-25 16:37:52
