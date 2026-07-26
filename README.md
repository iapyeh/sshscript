# SSHScript

SSHScript is a Python library for system automation. It provides one API for
running commands locally, connecting to remote hosts over SSH, traversing
nested SSH connections, changing execution identity, interacting with console
programs, and transferring files.

SSHScript v3 is designed to be used primarily as a regular Python module.
The optional Dollar syntax remains available for concise `.spy` automation
files.

## Documentation

The current documentation is the
[SSHScript v3 Documentation](https://iapyeh.github.io/sshscript/v3a/).

## Installation

```sh
python3 -m pip install sshscript
```

Upgrade an existing installation:

```sh
python3 -m pip install --upgrade sshscript
```

Check the installed version:

```sh
python3 -c "import sshscript; print(sshscript.__version__)"
```

## Module API

### Execute a local command

```python
import sshscript

session = sshscript.Session()
try:
    stdout, stderr = session.exec_command(["hostname"])
    print(str(stdout).strip())
    print("exit code:", session.exitcode)
finally:
    session.close()
```

`Session.exec_command()` returns `(stdout, stderr)`. The latest result is also
available through `session.stdout`, `session.stderr`, and
`session.exitcode`.

Pass a list or tuple for structured direct execution:

```python
stdout, stderr = session.exec_command(
    ["python3", "-c", "print('ready')"]
)
```

String commands use quote-aware automatic shell detection. Pipelines,
redirection, expansion, assignments, and logical operators automatically
select a shell:

```python
stdout, stderr = session.exec_command(
    "printf 'alpha\nbeta\n' | grep beta"
)
assert str(stdout).strip() == "beta"
```

Use `shell=False` or `shell=True` when the execution mode must be explicit.
Use `shell="bash"` to select a particular shell.

### Connect to a remote host

`Session.connect()` returns a connected session. Commands inside its context
run on that host:

```python
import sshscript

session = sshscript.Session()
try:
    with session.connect("ops@example.net") as remote:
        stdout, stderr = remote.exec_command(["hostname"])
        print("remote host:", str(stdout).strip())
finally:
    session.close()
```

SSHScript also supports nested connections:

```python
with session.connect("ops@bastion.example.net") as bastion:
    with bastion.connect("db@db.internal") as database:
        stdout, stderr = database.exec_command(
            ["systemctl", "is-active", "postgresql"]
        )
```

Authentication options such as `password`, `port`, `pkey`, and `pkey_path`
can be passed to `connect()`. Prefer SSH agents, managed keys, or a secret
manager instead of hard-coding credentials.

### Privilege changes

Use context managers for a bounded privilege change:

```python
from getpass import getpass

with session.connect("ops@example.net") as remote:
    password = getpass("sudo password: ")
    with remote.sudo(password=password) as root:
        root.exec_command(["systemctl", "restart", "nginx"])
```

`Session.su()` provides the corresponding account-switching context.

### Interactive programs

`Session.enter()` handles programs that prompt for input:

```python
with session.enter("python3", prompt=">>>", exit="quit()") as console:
    console.input("print('hello')")
    console.expect("hello")
```

It can also answer a password prompt from a command such as `mysqldump`:

```python
from getpass import getpass

password = getpass("MySQL password: ")
with session.enter(
    "mysqldump -u backup -p app > /tmp/app.sql"
) as console:
    console.expect("password")
    console.input(password)
```

### Upload and download

File transfers use the active connected session:

```python
with session.connect("ops@example.net") as remote:
    remote.upload(
        "./release.tar.gz",
        "/var/tmp/releases/",
        makedirs=True,
    )
    source, destination = remote.download(
        "/var/tmp/report.txt",
        "./reports/",
    )
```

## Optional Dollar syntax

Dollar syntax is an additional interface for `.spy` files. It is useful when
command-shaped notation makes an operations script easier to read:

```python
# example.spy
$hostname
print($.stdout.strip())

with $.connect("ops@example.net"):
    $systemctl is-active nginx
    print($.stdout.strip())
```

Run the file with:

```sh
sshscript example.spy
```

In v3, a single `$` handles both direct commands and shell features such as
pipelines and redirection. The old `$$` form is retained only for
compatibility and is deprecated.

The Module API and Dollar syntax use the same session, connection, result,
console, and file-transfer implementation. New applications should start
with the Module API and adopt Dollar syntax only when its concise notation is
an advantage.

## Why SSHScript?

- One interface for local subprocesses and remote SSH execution.
- Nested SSH sessions without duplicating connection logic.
- Python data processing, exceptions, functions, packages, and threading.
- Explicit context managers for connections, privilege changes, and
  interactive programs.
- Direct access to stdout, stderr, and exit status.
- Optional command-oriented syntax without giving up the Python ecosystem.

## Common use cases

- Server provisioning and configuration.
- Deployment and operational testing.
- Backup and restore workflows.
- Monitoring, data collection, and reporting.
- Network and account administration.
- Troubleshooting and repetitive maintenance.

## Links

- [SSHScript v3 Documentation](https://iapyeh.github.io/sshscript/v3a/)
- [GitHub repository](https://github.com/iapyeh/sshscript)
- [PyPI package](https://pypi.org/project/sshscript/)
- [Paramiko](https://www.paramiko.org/)

## License

SSHScript is released under the MIT License.
