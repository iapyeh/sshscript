---
title: "$.upload and $.download"
parent: "Advanced"
nav_order: 2
---

# $.upload and $.download

`$.upload` and `$.download` transfer one file through the active SSH
connection using SFTP. Both methods require an active
[`$.connect`](../Basic/connect) context; they do not apply to the local
session.

## Upload a file

Pass a local source file and its destination path on the remote host:

```python
with $.connect("ops@example.net"):
    src, dst = $.upload(
        "./build/sshscript.whl",
        "/tmp/sshscript.whl",
    )
    print(f"uploaded {src} to {dst}")
```

The source is normalised to an absolute local path. It must exist and be a
regular file; otherwise `FileNotFoundError` or an SSHScript exception is
raised.

To upload into an existing remote directory, pass that directory as
`dst`. SSHScript uses the local filename:

```python
with $.connect("ops@example.net"):
    $.upload("./config/nginx.conf", "/etc/nginx/conf.d/")
```

The connection account must have write permission to the final remote path.
If a privileged destination is needed, upload to a writable staging location
first, then move it with [`$.sudo`](../Basic/sudo).

```python
with $.connect("ops@example.net"):
    $.upload("./config/nginx.conf", "/tmp/nginx.conf")
    with $.sudo():
        $install -m 0644 /tmp/nginx.conf /etc/nginx/conf.d/example.conf
```

## Create missing remote directories

By default, a missing destination directory raises `FileNotFoundError`.
Set `makedirs=True` to create the required remote directory path:

```python
with $.connect("ops@example.net"):
    $.upload(
        "./reports/summary.txt",
        "/var/tmp/sshscript/reports/",
        makedirs=True,
    )
```

When `makedirs=True`, a destination that looks like a directory receives the
source filename. For unambiguous behaviour, include the complete destination
filename when the directory name could be mistaken for a file:

```python
with $.connect("ops@example.net"):
    $.upload(
        "./reports/summary.txt",
        "/var/tmp/sshscript/reports/summary.txt",
        makedirs=True,
    )
```

## Control overwriting

`overwrite=True` is the default. Use `overwrite=False` when an existing
remote file must be protected:

```python
try:
    with $.connect("ops@example.net"):
        $.upload(
            "./release.tar.gz",
            "/var/tmp/release.tar.gz",
            overwrite=False,
        )
except FileExistsError:
    print("The remote release already exists; it was not replaced.")
```

If overwriting is intended, verify the transferred content using a remote
command:

```python
with $.connect("ops@example.net"):
    $.upload("./version.txt", "/var/tmp/version.txt")
    $cat /var/tmp/version.txt
    print($.stdout)
```

## Download a file

`$.download(remote_source, local_destination=None)` returns
`(remote_source, local_destination)`.

```python
with $.connect("ops@example.net"):
    src, dst = $.download(
        "/var/log/nginx/access.log",
        "./downloads/",
    )
    print(f"downloaded {src} to {dst}")
```

If the local destination is an existing directory, SSHScript appends the
remote basename. If it is a filename, that exact local filename is used:

```python
with $.connect("ops@example.net"):
    $.download("/var/log/nginx/error.log", "./downloads/error-latest.log")
```

Omitting `dst` downloads the remote file to the current local working
directory:

```python
with $.connect("ops@example.net"):
    $.download("/var/tmp/diagnostics.tar.gz")
```

The local parent directory must already exist. Choose an explicit filename
when preserving an existing local file matters, because the underlying SFTP
transfer writes to the chosen path.

## Verify and handle errors

The returned paths make a simple local verification straightforward:

```python
import os

with $.connect("ops@example.net"):
    remote_path, local_path = $.download(
        "/var/tmp/diagnostics.tar.gz",
        "./downloads/",
    )

assert os.path.isfile(local_path)
assert os.path.getsize(local_path) > 0
```

Missing source files, inaccessible locations, and network failures are
reported as Python or SFTP exceptions. Handle those exceptions at the
operation boundary, clean up staged files, and avoid transferring sensitive
data to unprotected local paths.

## Nested connections

Transfers always use the current connection. This also works after connecting
through a bastion:

```python
with $.connect("ops@bastion.example.net"):
    with $.connect("db@db.internal"):
        $.download("/var/tmp/db-health.txt", "./downloads/")
```

The local source and destination paths remain paths on the machine running
SSHScript; only the transfer's remote side follows the active SSH session.

Last Updated: 2026-07-25 16:59:40
