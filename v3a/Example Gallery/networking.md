---
title: "Networking"
parent: "Example Gallery"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
---

# Networking

This collection starts with a single-endpoint TCP probe from a remote host. Add
future networking cases as separate Gallery pages, with an explicit target,
authorization, timeout, data-capture, and cleanup policy.

## Case: probe one TCP endpoint from a remote host

| Field | Value |
| --- | --- |
| Safety | Probes one authorized hostname/port; no scanning |
| Interface | Module API |
| Target | SSH host with `python3` and network access to the endpoint |
| Privilege | Ordinary account |
| Effects | One verified SSH connection and one bounded TCP connection request |

### Goal

Determine whether one authorized host and port can be reached from the network
view of an SSH target. The endpoint is passed as data, not shell syntax.
`socket.create_connection()` may try more than one resolved address in
sequence before it succeeds or fails.

### Prerequisites

- explicit authorization to connect to the endpoint;
- SSHScript 3.1.4 and Python 3.11 or newer on the runner;
- `python3` on the remote host;
- the SSH host's verified key in `known_hosts`; and
- a firewall policy that permits the intended test.

This is not a port scanner. Do not loop over unapproved addresses or ports.

### Complete script

Save as `remote_tcp_probe.py`:

```python
#!/usr/bin/env python3
import argparse
import shlex

from sshscript import Session


PROBE = """\
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
timeout = float(sys.argv[3])
with socket.create_connection((host, port), timeout=timeout) as sock:
    peer = sock.getpeername()
    print(f"connected to {peer[0]}:{peer[1]}")
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ssh_target", help="user@host or host")
    parser.add_argument("endpoint")
    parser.add_argument("port", type=int)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not 0 < args.connect_timeout <= 30:
        parser.error("connect timeout must be greater than 0 and at most 30")

    command = shlex.join([
        "python3",
        "-c",
        PROBE,
        args.endpoint,
        str(args.port),
        str(args.connect_timeout),
    ])

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
                timeout=args.connect_timeout + 5,
            )
            status = remote.exitcode
    except BaseException as primary:
        if not local.close():
            primary.add_note("SSHScript cleanup also failed")
        raise
    else:
        local.close(strict=True)

    if status != 0:
        raise SystemExit(f"probe failed with exit status {status}")
    if str(stderr):
        raise SystemExit("probe produced unexpected stderr")
    print(str(stdout).strip())


if __name__ == "__main__":
    main()
```

Run one approved probe:

```sh
python3 remote_tcp_probe.py ops@jump.example.net db.internal.example 5432
```

### Expected result

A successful run exits with status 0 and prints a single resolved peer:

```text
connected to 192.0.2.25:5432
```

DNS, routing, refusal, and timeout failures produce a nonzero remote Python
status. The example deliberately does not relay the raw remote stderr because
it can reveal internal names and addresses. Capture it only in a controlled,
redacted diagnostic path.

The remote `exec_command(timeout=...)` value is a Paramiko channel I/O timeout,
not a total command deadline. The probe itself enforces its socket-connect
timeout. A production workflow should also have an external overall deadline.

### Verification and cleanup

Confirm that the endpoint log shows one expected connection from the SSH
target. The socket closes when the remote Python `with` block exits. No remote
files or persistent configuration are created, so rollback is not required. If
the result is used as a deployment gate, record only a sanitized endpoint
identifier and status.

### Adapt this case

Keep future probes narrowly scoped. TLS validation, HTTP requests, DNS
inspection, packet capture, and firewall changes have different permissions
and data exposure; publish each as its own case with protocol-specific
verification and cleanup.

Last Updated: 2026-09-25 16:37:52
