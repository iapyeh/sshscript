---
title: "Dollar Syntax Reference"
parent: "Reference"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 2
---

# Dollar Syntax Reference

Dollar syntax is SSHScript v3.1's optional shorthand for `.spy` files. It
uses the same Session implementation as the primary Python API, but lets an
automation script place `$` before a command.

Use [Running Commands and Shell Pipelines](../../module/) for libraries,
applications, and ordinary Python projects. Use Dollar syntax when concise,
shell-like operational steps
improve the readability of a standalone script.

## Execute commands and read results

```python
$hostname
print($.stdout.strip())

$python3 -c "import sys; sys.stderr.write('problem\\n'); sys.exit(7)"
print($.exitcode)        # 7
print($.stderr.strip())  # problem
```

Each command updates `$.stdout`, `$.stderr`, and `$.exitcode`. Capture the
two output streams when the values must survive a later command:

```python
stdout, stderr = $python3 -c "import sys; print('out'); sys.stderr.write('err\\n')"
```

## Command forms

```python
$hostname
$'printf string-literal'
$r'printf raw-string'

command = "python3 -c \"print('from a variable')\""
$(command, timeout=5)

name = "SSHScript"
$f'printf "Hello, %s\\n" {name}'
```

The value passed to `$(...)` must be a non-empty string. Lists and tuples
raise `TypeError`, just as they do with `Session.exec_command()`.

Quote dynamic values before inserting them into a shell command:

```python
import shlex

folder = "/tmp/a folder"
$f'mkdir -p {shlex.quote(folder)}'
```

For argument-preserving execution, assemble an argument list with
`shlex.join()` and use `shell=False`:

```python
arguments = ["printf", "%s\n", "hello world"]
$(shlex.join(arguments), shell=False)
```

## Automatic shell selection

V3.1 inspects the final command string with quote awareness. Plain commands
use argument-preserving mode. Pipelines, redirection, logical operators,
assignments, globbing, expansion, and command substitution automatically
select a shell.

```python
$printf 'alpha\\nbeta\\n' | grep beta
$VALUE=ready; printf '%s\\n' "$VALUE"
$printf 'report\\n' > /tmp/sshscript-report.txt
$printf 'host: %s\\n' "$(hostname)"
```

Shell operators inside quotes do not select shell mode. A dollar expression
inside single quotes remains literal:

```python
$echo '$HOME'
assert $.stdout.strip() == "$HOME"
```

Override selection when required:

```python
command = 'python3 -c "import sys; print(sys.argv[1:])" "|" "cat"'
$(command, shell=False)

$("printf 'POSIX shell\\n'", shell=True)
bash_command = (
    '[[ -n "$BASH_VERSION" ]] '
    '&& printf "%s\\n" "$BASH_VERSION"'
)
$(bash_command, shell="bash")
$(bash_command, shell=True, shell_executable="bash")
```

`shell_executable=` chooses the executable used when shell mode is active; it
does not by itself force a plain command into shell mode.

On a local Session, `shell=False` launches the parsed argument vector without
a shell. On a remote Session, SSHScript safely re-quotes the vector and sends
`exec ...` through the SSH server's command shell. Operators remain literal
arguments rather than user shell syntax, but a server-side shell still
participates.

## One `$` replaces former `$$`

Older documents use `$$` to force a shell:

```python
$$ls -l | grep '^d'
```

Write new v3.1 scripts with one Dollar:

```python
$ls -l | grep '^d'
```

The `$$` form remains temporarily compatible but is deprecated and forces
shell mode.

## Session contexts

The notation is unchanged inside remote and privileged contexts:

```python
$hostname  # localhost

with $.connect("ops@example.net"):
    $hostname
    with $.sudo(password=password):
        $systemctl status nginx
```

## Developer tests

The source checkout includes a localhost-only smoke suite:

```sh
python3 sshscript.py unittest/dollar_syntax.spy
```

It does not load credentials, connect to an SSH server, use an SSH agent, or
read a private key. See [Contributing and Testing](../../development-and-testing/)
for the unittest wrapper, full release gate, and language integration modes.

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

Last Updated: 2026-09-21 17:45:03
