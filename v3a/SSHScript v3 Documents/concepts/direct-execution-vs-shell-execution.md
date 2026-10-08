---
title: "Direct Execution vs Shell Execution"
parent: "Concepts"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
permalink: /v3a/concepts/direct-execution-vs-shell-execution/
---

# Direct Execution vs Shell Execution

> **Version scope:** The argv/CommandResult/check/config API is available in 3.1.5.
> Session settings and managed jobs/deadlines are features available in 4.0.1.
> Use the [canonical API guide]({{ site.baseurl }}/v3a/recommended-api/) to choose
> examples for your installed version.

`Session.exec_command()` accepts a nonempty command string or a list/tuple of
string arguments. Sequences always use direct mode and disallow shell mode.
For strings, `shell` selects argument-preserving execution or shell parsing.

```python
stdout, stderr, exitcode = session.exec_command(
    command,
    shell=None,
    shell_executable=None,
)
```

## Selection modes

| Setting | Meaning |
| --- | --- |
| `shell=None` | Default. Inspect the final string and select direct or shell execution. |
| `shell=False` | Force argument-preserving direct execution. |
| `shell=True` | Force `/bin/sh -c`. |
| `shell="bash"` | Force `bash -c`; shorthand for `shell=True, shell_executable="bash"`. |

Supplying both a string-valued `shell` and `shell_executable` raises
`ValueError`. Prefer an explicit choice whenever correctness or security
depends on the mode.

## Direct execution

Pass the argument sequence directly; quoting it with `shlex.join()` and
forcing `shell=False` also remains supported:

```python
arguments = [
    "python3",
    "-c",
    "import sys; print(sys.argv[1])",
    "hello; not shell syntax",
]
result = session.exec_command(arguments, check=True)
stdout, stderr, exitcode = result
```

Locally, SSHScript passes argv directly to `subprocess.run()`. When a caller
supplies a string with `shell=False`, it first parses it with `shlex.split()`.

The SSH protocol accepts a command string, not an argument array. Over SSH,
SSHScript parses locally, quotes each argument, and sends an `exec ...` command
through the server's command shell. Operators remain arguments instead of
becoming user-requested shell syntax, but a server-side shell still
participates.

Direct mode preserves argument boundaries; it is not a sandbox. The selected
program can still interpret its own arguments, configuration, or input.

## Shell execution

Use shell mode for pipelines, redirection, expansion, variables, and other
shell language:

```python
session.exec_command(
    "printf 'alpha\nbeta\n' | grep beta",
    shell=True,
)

session.exec_command(
    '[[ -n "$BASH_VERSION" ]] && printf "%s\n" "$BASH_VERSION"',
    shell="bash",
)
```

The default shell executable is `/bin/sh`. Select Bash only when the command
requires Bash grammar.

Quote each dynamic data value separately:

```python
import shlex


command = "printf '%s\n' " + shlex.quote(external_value)
session.exec_command(command, shell=True)
```

Quoting preserves the data boundary. It does not authorize an executable,
operation, path, or value. Automatic detection is also a convenience, not an
input-sanitization boundary.

## What automatic detection recognizes

With `shell=None`, quote-aware detection selects a shell for features including:

- pipelines, `&&`, `||`, background `&`, and command separators;
- input and output redirection;
- parameter expansion and command substitution;
- globbing and tilde expansion;
- comments at the beginning of a shell word;
- subshell parentheses;
- initial variable assignments;
- shell builtins and reserved words; and
- newlines or incomplete quoting.

Operators inside quotes can remain literal. Parameter and command expansion are
active inside double quotes but suppressed inside single quotes:

```python
session.exec_command("python3 -c \"print('a|b')\"")
# Direct: the pipe is quoted.

session.exec_command("echo '$HOME'")
# Direct: single quotes suppress expansion.

session.exec_command('echo "$HOME"')
# Shell: parameter expansion is active.

session.exec_command("false || printf recovered")
# Shell: logical operator.
```

Detection examines the final string. If external input contributes `;`, `|`,
`$()`, redirection, or another recognized construct, it can change automatic
selection to shell mode. Pass argv directly for dynamic
argument lists.

The detector is a bounded heuristic, not a complete parser for every installed
shell. Use an explicit mode when semantics depend on interpretation.

## Local and remote differences

| Concern | Local | Remote |
| --- | --- | --- |
| `shell=False` | `subprocess.run(shlex.split(command))` | Per-argument quoting followed by remote `exec ...` |
| Shell mode | Selected executable with `-c` | Quoted selected executable with `-c` |
| Missing direct executable | Usually raises `FileNotFoundError` | Usually returns a nonzero status |
| `env=` | Merged with the local process environment | Requested as SSH environment values; server policy may reject them |
| `check=True` | CalledProcessError after result capture | Same policy after result capture |

Both backends return CommandResult (stdout, stderr, exitcode when unpacked).
Choose `check=True` for automatic failure exceptions or inspect the saved status.

String `input=` also differs slightly: remote string input receives a trailing
newline when absent, then the SSH write side closes. Test protocol-sensitive
programs on both backends.

## One-shot commands do not share state

```python
session.exec_command("cd /tmp", shell=True)
stdout, stderr, exitcode = session.exec_command("pwd", shell=False)
# The second command is a new process and need not print /tmp.
```

Use a persistent shell for shared working directory, environment, functions, or
similar state:

```python
with session.shell() as shell:
    shell.exec_command("cd /tmp")
    if shell.exitcode != 0:
        raise RuntimeError("cd /tmp failed")

    shell.exec_command("export MODE=staging")
    if shell.exitcode != 0:
        raise RuntimeError("setting MODE failed")

    stdout, stderr, exitcode = shell.exec_command(
        "printf '%s:%s\\n' \"$PWD\" \"$MODE\""
    )
    status = shell.exitcode
    saved_stdout, saved_stderr = str(stdout), str(stderr)
    if status != 0:
        raise RuntimeError(f"printf failed with exit status {status}")
```

`session.shell()` starts a persistent process, `bash -i` by default. Commands
sent to that console are interpreted by the running shell; they do not repeat
one-shot automatic detection.
The block's scope covers the shell lifecycle, not an aggregate success check.
Each required command must be checked before the next command replaces the
latest status. 4.0 console calls return immutable CommandResult snapshots with
three-value unpacking; published 3.1.5 retains the two-buffer contract. See [Results and Error Model]({{ site.baseurl }}/v3a/concepts/results-and-error-model/)
for a reusable checked-console helper and the distinction between returning
from an interaction and completing a process.


The `shell=` option on `enter()`, `su()`, and `sudo()` has another purpose: it
chooses whether the interactive program is layered on a base shell or started
directly.

## Dollar syntax shares this path

```python
$printf 'alpha\nbeta\n' | grep beta

arguments = ["printf", "%s", external_value]
$(arguments, check=True)

$('printf "%s\n" "$HOME"', shell=True)
$('printf "%s\n" "$BASH_VERSION"', shell="bash")
```

`$command` uses automatic detection. The old `$$` form is deprecated because
one `$` now handles shell features through automatic or explicit selection.

See
[Running Commands and Shell Pipelines]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/module/)
for task-oriented examples and
[Host Keys, Credentials, and Command Injection](../../security-and-operations/host-keys-credentials-and-command-injection/)
for security review.

Last Updated: 2026-10-08 23:48:09
