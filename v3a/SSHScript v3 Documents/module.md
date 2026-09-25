---
title: "Running Commands and Shell Pipelines"
parent: "How-to Guides"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 1
---

# Running Commands and Shell Pipelines

Use the regular Python `Session` API to run one-shot commands with preserved
argument boundaries or through an explicitly selected shell. This is
SSHScript v3.1's primary interface for applications, libraries, tests, and
ordinary `.py` files.

## Create and close a Session

```python
from sshscript import Session

session = Session()
try:
    stdout, stderr = session.exec_command("hostname", shell=False)
    print(str(stdout).strip())
    print(session.exitcode)
finally:
    session.close(strict=True)
```

A new `Session` runs commands on localhost. Construction is side-effect free:
it does not globally patch Python imports, warnings, logging, or
`threading.Thread`.

`close()` is repeatable. By default cleanup failures are recorded in
`session.close_errors`; `close(strict=True)` raises when cleanup could not be
completed.

## Commands are strings

`Session.exec_command(command)` accepts exactly one non-empty `str`. Lists,
tuples, and other command types raise `TypeError`.

Build arguments with `shlex.join()` when shell expansion is not required:

```python
import shlex

arguments = ["python3", "-c", "print('hello world')"]
command = shlex.join(arguments)
stdout, stderr = session.exec_command(command, shell=False)
```

This keeps spaces and shell metacharacters inside individual arguments. Do
not pass `arguments` itself to `exec_command()`.

`Session.onedollar()` is a deprecated compatibility alias and follows the
same string-only rule. New Python code should call `exec_command()`.

## Shell selection

With the default `shell=None`, SSHScript inspects the final command string.
Plain commands use argument-preserving mode; pipelines, redirection,
expansion, assignments, and other shell syntax select a shell automatically.

```python
session.exec_command("uname -a", shell=False)
session.exec_command("printf 'alpha\\nbeta\\n' | grep beta")
session.exec_command("printf '%s\\n' \"$HOME\"", shell=True)
session.exec_command(
    '[[ -n "$BASH_VERSION" ]] && printf "%s\\n" "$BASH_VERSION"',
    shell="bash",
)
```

Use `shell=False` for safely quoted argument strings, `shell=True` to force
the POSIX shell, or `shell="bash"` only when a command needs Bash features.
On localhost, `shell=False` launches the parsed argument vector without a
shell. Over SSH, SSHScript safely re-quotes that vector and sends `exec ...`
through the server's command shell; operators remain arguments rather than
user shell syntax, but a server-side shell still participates.

## Results

Every command returns `(stdout, stderr)` and updates the Session's latest
result:

```python
stdout, stderr = session.exec_command(
    "python3 -c \"import sys; print('out'); "
    "sys.stderr.write('err\\n'); sys.exit(7)\""
)

print(str(stdout).strip())
print(str(stderr).strip())
print(session.exitcode)  # 7
```

The next command replaces `session.stdout`, `session.stderr`, and
`session.exitcode`, so keep values needed later in Python variables.

## Remote Sessions

`connect()` returns a child Session. The same `exec_command()` API then runs
on the selected host:

```python
from sshscript import Session

local = Session()
try:
    with local.connect("ops@example.net") as remote:
        stdout, stderr = remote.exec_command("hostname", shell=False)
        print(str(stdout).strip())
finally:
    local.close(strict=True)
```

Connections can be nested for bastion-host workflows. See
[Connections, Authentication, and Bastions](../Basic/connect/) for
authentication and host-key verification.

## Script helpers

`sshscript.run_script(source)` runs in-memory Python or Dollar syntax in a
new local Session. `sshscript.run_file(path)` runs exactly one existing
regular Python or `.spy` file:

```python
import sshscript

status = sshscript.run_file("automation.spy")
```

Directories, globs, iterables, and multiple paths are not accepted. Compose
larger automation through ordinary Python imports; `run_file()` temporarily
enables peer `.spy` imports as well.

## Next steps

- Follow the [Module API Tutorial](../tutorial/).
- Learn [CLI and Environment Variables](../cli-and-environment/).
- Review [Contributing and Testing](../development-and-testing/).
- Use the [Dollar Syntax Reference](../Basic/dollar/) only when concise `.spy`
  notation is useful.

## Runtime validation

Commands must be nonempty strings; wrong types raise `TypeError`, and empty
commands raise `ValueError`. Persistent commands must contain only one line.
`get_pty` accepts only `None` or bool. The internal `for_with` selector accepts
only bool. Text matching rejects compiled bytes regular expressions with
`TypeError`; appended output must be str.

Invalid console/channel lifecycle transitions raise `RuntimeError`. Failed
listener removal, duplicate hijack/release, and last-layer removal preserve
state. Closed channel operations raise `BrokenPipeError`; a channel ending
while a caller waits raises `EOFError`; timeout raises `TimeoutError`.
Disconnected `Session.sftp`, upload, and download raise `SSHScriptException`.
Paramiko failures retain their original exception and traceback. See
[Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

## Assertions and production command checks

User-written `assert` statements in `.spy` files retain normal Python semantics.
`python -O` removes them, including calls inside the assertion. They are useful
for illustrative tests, but production scripts must explicitly inspect
`session.exitcode` (or `$.exitcode`) and handle nonzero status. Local
`Session.exec_command(..., check=True)` raises `subprocess.CalledProcessError`;
this is not a portable remote-command option. SSH, timeout, and transport
failures remain exceptions regardless of optimization.

`AssertionError` was never a supported SSHScript API contract. Package runtime
validation now uses explicit exceptions in both normal and optimized modes.
See [Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

Last Updated: 2026-09-25 16:37:52
