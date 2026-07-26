---
title: "$"
parent: "Basic"
nav_order: 1
---

# $

`$` is SSHScript's command syntax. It runs a command in the current session:
locally by default, or on the host selected by [`$.connect`](connect).

SSHScript v3 uses one-dollar syntax for both ordinary commands and shell
features. The former `$$` syntax remains only for compatibility and is
deprecated.

## Execute commands and read their result

```python
$hostname
print($.stdout.strip())

$python3 -c "import sys; sys.stderr.write('problem\\n'); sys.exit(7)"
print($.exitcode)       # 7
print($.stderr.strip()) # problem
```

Each command updates these properties:

| Property | Meaning |
| --- | --- |
| `$.stdout` | Standard output |
| `$.stderr` | Standard error |
| `$.exitcode` | Process exit status |

Capture both output streams directly when useful:

```python
stdout, stderr = $python3 -c "import sys; print('out'); sys.stderr.write('err\\n')"
assert stdout.strip() == "out"
assert stderr.strip() == "err"
```

The next command replaces `$.stdout`, `$.stderr`, and `$.exitcode`; keep
anything needed later in a Python variable.

## Command forms

Use the direct form for a literal command. Use `$()` for a variable command
or command options:

```python
command = "python3 -c \\"print('from a variable')\\""
$(command, timeout=5)

name = "SSHScript"
$f'printf "Hello, %s\\n" {name}'

$'printf string-literal'
$r'printf raw-string'
```

Quote dynamic values before inserting them into a shell command:

```python
import shlex
folder = "/tmp/a folder"
$f'mkdir -p {shlex.quote(folder)}'
```

## Automatic shell detection

V3 inspects string commands with quote awareness. Plain commands execute
directly. Shell syntax automatically selects a shell, including pipelines,
redirection, logical operators, environment-variable or tilde expansion,
globs, assignments, and command substitution.

```python
$printf 'alpha\\nbeta\\n' | grep beta
assert $.stdout.strip() == "beta"

$VALUE=ready; printf '%s\\n' "$VALUE"
$printf 'report\\n' > /tmp/sshscript-report.txt
$printf 'host: %s\\n' "$(hostname)"
```

Characters inside quotes remain literal, so this is direct execution and
prints `$HOME` rather than expanding it:

```python
$echo '$HOME'
assert $.stdout.strip() == "$HOME"
```

Override automatic selection when required:

```python
# Quoted shell-looking characters remain ordinary arguments in direct mode.
command = 'python3 -c "import sys; print(sys.argv[1:])" "|" "cat"'
$(command, shell=False)

$(command, shell=True)                    # force the POSIX shell
$('printf bash-shell', shell='bash')      # select Bash
```

`shell_executable='bash'` is equivalent to `shell='bash'`. The command passed
to `$()` must be a string.

## Migrating from `$$`

Older documents use `$$` for a shell command:

```python
$$ls -l | grep '^d'
```

Write the v3 form with one dollar:

```python
$ls -l | grep '^d'
```

Use `$` for all new scripts. It chooses direct execution when possible and a
shell only when the command needs one.

## Local and remote sessions

The syntax is unchanged inside a connection block:

```python
$hostname  # local host

with $.connect("ops@example.net"):
    $hostname  # remote host
```

See [`$.connect`](connect) for authentication and nested connections.

## Developer self-tests

The SSHScript source checkout includes a credential-free smoke suite for
dollar syntax:

```text
unittest/dollar_syntax.spy
```

It runs only local subprocesses. It does not load `localsecret.py` or
`secret.py`, connect to an SSH server, use an SSH agent, or read a
private key. Run it from the root of the SSHScript source checkout:

```sh
python3 sshscript.py unittest/dollar_syntax.spy
```

The suite checks:

- bare, string, raw-string, expression, and f-string command forms;
- command assignment and `$.stdout`, `$.stderr`, and
  `$.exitcode`;
- automatic shell selection for pipelines, assignments, operators,
  expansion, and redirection;
- string commands plus explicit `shell=False` and `shell=True`;
- dollar commands inside Python functions;
- a persistent local shell created with `with $(...)`; and
- importing another `.spy` module that contains dollar syntax.

## Run through Python unittest

A standard-library wrapper runs the same `.spy` suite in an isolated
subprocess. It creates an empty temporary home directory and removes
SSH-agent environment variables, ensuring that the test remains independent
of the developer's SSH configuration:

```sh
python3 -m unittest discover -v -s unittest \
  -p 'test_sshscript_dollar_syntax.py'
```

To run this suite together with the regular [Module](../module) API tests:

```sh
python3 -m unittest discover -v -s unittest -p 'test_sshscript_*.py'
```

The command returns a non-zero status if any check fails. These tests are a
quick local regression check; SSH integration tests remain separate because
they require explicit host credentials and configuration.

Last Updated: 2026-07-26 16:53:25
