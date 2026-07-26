---
title: "Module API Tutorial (EN)"
parent: "SSHScript v3 Documents"
nav_order: 2
---

# Module API Tutorial (EN)

Start with SSHScript as a regular Python module. The Dollar syntax is an
optional concise notation for `.spy` files.

## Create a Session

```python
import sshscript

session = sshscript.Session()
try:
    stdout, stderr = session.exec_command(["hostname"])
    print(str(stdout).strip())
finally:
    session.close()
```

The latest command result is available as `session.stdout`,
`session.stderr`, and `session.exitcode`.

## Execute local commands

Use a list for structured arguments. Strings automatically use a shell when
they contain a pipeline, redirect, expansion, or logical operator.

```python
stdout, stderr = session.exec_command(["python3", "-c", "print('ready')"])
stdout, stderr = session.exec_command("printf 'alpha\\nbeta\\n' | grep beta")
```

Use `shell=False` or `shell=True` to override automatic selection.

## Connect and compose contexts

```python
with session.connect("ops@example.net") as remote:
    remote.exec_command(["hostname"])

    with remote.sudo(password="obtained securely") as root:
        root.exec_command("systemctl restart nginx")
```

Connections can be nested for bastion hosts. The returned session is the
object that runs commands, transfers files, and opens interactive programs.

## Interactive programs and files

```python
with session.connect("ops@example.net") as remote:
    with remote.enter("python3", prompt=">>>", exit="quit()") as console:
        console.input("print('hello')")
        console.expect("hello")

    remote.upload("./release.tar.gz", "/var/tmp/", makedirs=True)
    remote.download("/var/tmp/report.txt", "./reports/")
```

## Optional Dollar syntax

For a standalone `.spy` automation file, the same model can be written
more concisely:

```python
with $.connect("ops@example.net"):
    $systemctl restart nginx
```

Run it with `python3 sshscript.py maintenance.spy`. See
[Dollar Syntax Add-on](Basic/dollar) only when this notation suits the team.

Last Updated: 2026-07-25 16:59:40
