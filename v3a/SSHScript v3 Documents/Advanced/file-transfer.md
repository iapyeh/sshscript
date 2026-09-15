---
title: "Session.upload() and Session.download()"
parent: "Advanced Session API"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
---

# Session.upload() and Session.download()

`upload()` and `download()` transfer one file through a connected Session
using SFTP. They are not available on a localhost-only Session.

## Upload a file

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        source, destination = remote.upload(
            "./build/sshscript.whl",
            "/var/tmp/sshscript.whl",
        )
        print(f"uploaded {source} to {destination}")
finally:
    local.close(strict=True)
```

The local source is normalized to an absolute path and must be an existing
regular file. Passing an existing remote directory as `dst` preserves the
local filename:

```python
with local.connect("ops@example.net") as remote:
    remote.upload("./config/nginx.conf", "/var/tmp/")
```

The connection account must be able to write the remote destination. For a
privileged path, upload to a writable staging location and publish it inside
a controlled `sudo()` context:

```python
with local.connect("ops@example.net") as remote:
    remote.upload("./config/nginx.conf", "/tmp/nginx.conf")
    with remote.sudo(password=password) as root:
        root.exec_command(
            "install -m 0644 /tmp/nginx.conf "
            "/etc/nginx/conf.d/example.conf"
        )
```

## Create remote directories

A missing destination directory normally raises `FileNotFoundError`. Set
`makedirs=True` to create the required remote path:

```python
with local.connect("ops@example.net") as remote:
    remote.upload(
        "./reports/summary.txt",
        "/var/tmp/sshscript/reports/",
        makedirs=True,
    )
```

For unambiguous behavior, supply the complete destination filename when a
directory name might look like a file:

```python
remote.upload(
    "./reports/summary.txt",
    "/var/tmp/sshscript/reports/summary.txt",
    makedirs=True,
)
```

## Replacement safety

`overwrite=True` is the default. `overwrite=False` adds a pre-transfer check
for resolved existing destinations, but it is not an atomic server-side
create operation. When replacement must be impossible, choose a unique
staging name and publish it with a server-side policy or atomic rename after
verification.

## Download a file

`download(remote_source, local_destination=None)` returns the resolved
`(remote_source, local_destination)` pair:

```python
import os

os.makedirs("./downloads", exist_ok=True)

with local.connect("ops@example.net") as remote:
    source, destination = remote.download(
        "/var/log/nginx/access.log",
        "./downloads/",
    )
    print(f"downloaded {source} to {destination}")
```

If the local destination is an existing directory, SSHScript appends the
remote basename. If it is a filename, that exact filename is used:

```python
remote.download(
    "/var/log/nginx/error.log",
    "./downloads/error-latest.log",
)
```

Omitting `dst` downloads into the current local working directory. The local
parent directory must already exist.

## Verify transfers

```python
import os

with local.connect("ops@example.net") as remote:
    remote_path, local_path = remote.download(
        "/var/tmp/diagnostics.tar.gz",
        "./downloads/",
    )

if not os.path.isfile(local_path) or os.path.getsize(local_path) == 0:
    raise RuntimeError("downloaded file is missing or empty")
```

Missing paths, permissions, and network failures are reported as Python or
SFTP exceptions. Handle them at the transfer boundary and remove temporary
files containing sensitive data.

## Nested connections

Transfers always use the current connected Session:

```python
with local.connect("ops@bastion.example.net") as bastion:
    with bastion.connect("db@db.internal") as database:
        database.download(
            "/var/tmp/db-health.txt",
            "./downloads/",
        )
```

Local paths remain on the machine running SSHScript; only the remote side
follows the active connection.

## Optional Dollar syntax

```python
with $.connect("ops@example.net"):
    $.upload("./release.tar.gz", "/var/tmp/")
    $.download("/var/tmp/report.txt", "./reports/")
```

The shorthand calls the same transfer methods on the current Session.

Last Updated: 2026-09-14 18:02:02
