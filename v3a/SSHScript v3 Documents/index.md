---
title: "SSHScript v3.1 Documentation"
nav_order: 1
has_children: true
---

# SSHScript v3.1 Documentation

SSHScript automates local and remote command-line work from Python. Version
3.1 uses the regular `Session` API as its primary interface, making it easy to
embed automation in applications, libraries, tests, and existing Python
projects.

The recommended learning path is the [Module API](module), followed by the
[Module API Tutorial](tutorial). The Core and Advanced sections cover
connections, privilege changes, interactive programs, transfers, streaming
output, and threads. The [Dollar Syntax Add-on](Basic/dollar) is optional and
is documented separately for concise `.spy` scripts.

SSHScript requires Python 3.9 or newer:

```sh
python3 -m pip install sshscript
```

Version 3.1 is currently beta. Its default release gate is credential-free;
run real SSH scenarios only in an isolated environment with explicit local
configuration.

Last Updated: 2026-09-14 18:02:02
