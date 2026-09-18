---
title: "Uploading and Downloading Files"
parent: "How-to Guides"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 6
---

# Uploading and Downloading Files

`upload()` and `download()` transfer one file through a connected Session
using SFTP. Both require an active SSH connection. A localhost-only Session,
a disconnected Session, or a Session without an active transport raises
`SSHScriptException` before resolving paths or accessing files:

- `upload() requires an active SSH connection`
- `download() requires an active SSH connection`

Establish a connection with `connect()` before calling either method. This
check remains active with Python's `-O` option. If the connection drops after
the check, the exception from the actual SFTP operation propagates.

## Results and error handling

Both methods return `(source, destination)` after a successful transfer.
Failures raise Python or SFTP exceptions; they do not return a failure exit
code. For example, handle a file or permission error at the transfer call:

```python
try:
    source, destination = remote.download("/var/log/app.log", "./app.log")
except OSError as exc:
    print(f"Download failed: {exc}")
else:
    print(f"Downloaded {source} to {destination}")
```

Other SSH or connection exceptions can propagate as well; the example above
only handles `OSError` and its subclasses.

Transfers do not update `stdout`, `stderr`, or `exitcode`, including the
`$.stdout`, `$.stderr`, and `$.exitcode` shorthand. These properties describe
the last command execution. After a transfer, `$.exitcode` still holds that
command's exit code, or raises `ValueError` if no command result exists.
Do not use it to decide whether an upload or download succeeded.

## Account permissions inside `su()` and `sudo()`

SFTP uses the account that authenticated the current SSH connection.
Entering `with $.su(...)` or `with $.sudo(...)` changes the account used by
commands in that console, but does not change the SFTP account. This also
applies to `Session.upload()` and `Session.download()`.

```python
with $.connect("ops@example.net"):
    with $.sudo(password=password):
        $whoami
        # The command may run as root, but SFTP still accesses files as ops.
        source, destination = $.download("/var/log/app.log", "./app.log")
```

The download succeeds only if `ops` has permission to read the remote file
and traverse its parent directories, even when `whoami` reports `root`.
Uploads likewise require the connection account's permissions to create or
write the remote destination. A transfer permission failure raises an
exception, rather than setting `$.exitcode`.

For privileged uploads, transfer to a location writable by the connection
account, then run `install` or `mv` through the privileged console. For
privileged downloads, use that console to prepare a temporary copy readable
by the connection account, download the copy, and clean it up afterward.
Local file access always uses the account running SSHScript on the local
machine; remote `su()` and `sudo()` do not change local permissions.

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

## Destination paths and parent directories

Upload destinations follow these rules, regardless of `makedirs`:

| Destination | Interpretation |
| --- | --- |
| Existing remote directory | Append the local source filename. |
| Path ending in `/` | Treat as a directory and append the local source filename. |
| Any other path | Use as the complete destination filename. |

Remote paths use POSIX `/` separators. Filename extensions do not determine
whether a destination is a directory. A trailing `/` on an existing regular
file raises `NotADirectoryError`.

`makedirs=True` creates missing parent directories for the resolved file;
its default, `False`, requires those directories to exist.

```python
# Create reports/ and preserve the source filename.
remote.upload("./summary.txt", "/var/tmp/reports/", makedirs=True)

# Create reports/ and rename the uploaded file, even to a different extension.
remote.upload("./summary.txt", "/var/tmp/reports/renamed.csv", makedirs=True)

# A nonexistent path without a trailing slash is a filename.
remote.upload("./summary.txt", "/var/tmp/report", makedirs=True)
```

**Migration:** older versions guessed directory intent from filename
extensions when `makedirs=True`. If a destination is a directory that may
not exist yet, add a trailing `/`. For example, change `/var/tmp/reports`
to `/var/tmp/reports/` to preserve directory intent.

## Replacement safety

`overwrite=True` is the default and permits replacing an existing file.
With `overwrite=False`, upload checks the resolved destination and raises
`FileExistsError` when it already exists, including a dangling symbolic
link. This applies with matching source/destination filenames and with
`makedirs=True` as well.

The actual write uses SFTP exclusive creation: if another process creates
the destination after the check, upload fails instead of overwriting it.
Some SFTP servers report this race as a generic `OSError` rather than
`FileExistsError`. Other permission, connection, and SFTP errors propagate;
there is no fallback to a write that permits overwriting.

```python
remote.upload("./summary.txt", "/var/tmp/reports/",
              makedirs=True, overwrite=False)
```

Exclusive creation prevents replacement; it does not make the entire
transfer atomic. A failed transfer can leave a partial new file. For atomic
publication, upload to a unique staging path and publish it separately using
an appropriate server-side operation. Download has no `overwrite` option
and can overwrite an existing local destination.

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

Last Updated: 2026-09-17 12:13:56
