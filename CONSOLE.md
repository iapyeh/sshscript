# Interactive console (7.0)

> **7.0.1 source contract.** Use the matching source checkout or verified wheel.
> A source push does not publish a GitHub Release or PyPI package.


The SSHScript 7.0 console runs from the flat development checkout:

```sh
python3 -B sshscript.py console
```

Use Python 3.11 or newer with the project's dependencies. Install
a matching 7.0.1 wheel or source distribution for `sshscript console`. No installation into the flat
development checkout is required.

## Embed an existing Session (new API)

Use the public `sshscript.Console` API for borrowed Sessions, host-driven updates,
credential hooks and explicit cleanup/reuse reporting. Read
[the embedded console contract](EMBEDDED_CONSOLE.md) and its executable examples.
The CLI uses the same Console core and ownership contract. Earlier 6.0 CLI
compatibility is not maintained; see the linked contract for removed entry points
and aliases. This guide describes the 7.0.1 release contract.

## A Python console with dollar syntax

Input is Python by default, with SSHScript dollar syntax available in the same
namespace. No Python/shell language-mode switching is required:

```text
local [user]> hostname
NameError: operation failed; use :error or :traceback for details.
local [user]> hostname = "a Python variable"
local [user]> hostname
'a Python variable'
local [user]> $hostname
my-host
local [user]> print($.stdout)
my-host
local [user]> actual_hostname = $.stdout.strip()
local [user]> options = {"port": 2222, "username": "ops", "timeout": 15}
local [user]> $.connect("my-ssh-alias", **options)
```

`hostname` reads a Python variable; `$hostname` executes a command. A shell
command always needs its dollar prefix. `$cd /tmp` and `$export NAME=value`
retain the shell's directory and environment for later dollar commands. Output
streams while a command runs; a nonzero exit status is displayed and the console
remains usable. Shell commands do not display an extra JobResult representation.

`$.stdout`, `$.stderr` and `$.exitcode` read the most recent dollar-command result
in the current managed layer. These are result snapshots, not drained live
buffers. The `result` Python name retains the latest dollar-command JobResult.
You can mix dollar properties with Python expressions and f-strings, or unpack
command results using the normal `.spy` syntax:

```text
local [user]> out, err, status = $printf ready
local [user]> summary = f"host={$.stdout.strip()}, status={$.exitcode}"
local [user]> for index in range(2):
...     $f"echo item-{index}"
...
```

On a terminal, the console enables Python's optional `readline` module for line
editing, including Backspace. Python builds without that module retain the
terminal's basic input editing; piped input does not require it. No history file
is written.

As in Python's REPL, a blank line completes an indented block. Parenthesized
expressions and parameter dictionaries can span multiple input lines. Functions
and variables remain available for later inputs. Ordinary Python strings that
contain dollar characters remain literal strings. `with` blocks use the normal
`.spy` compiler's lexical context management, rather than leaving a managed
interactive layer open after the block. Inside lexical contexts, inspect or
print returned command output explicitly, just as in a script.

Reserved names are `control`, `session` (current connection Session), `console`
(current shell/identity/program), `result` and `error` (latest operation error).
`session` and `console` are refreshed when environments change. User variables
survive environment changes; references to exited environments are not reusable.
`getpass` is provided for reading secrets without terminal echo. No input history
is saved by SSHScript; host terminal/session recording remains external.

## Connections and identities

A connection automatically enters its own persistent Bash shell. One `exit()`
closes that shell and connection together and restores the parent environment.
Nested connections are created by the current connection Session. They retain
the existing SSH config, key ownership and known-host verification contracts.

```sh
python3 -B sshscript.py console ops@host1 --port 2222 --timeout 15
python3 -B sshscript.py console my-ssh-alias --ask-pass
```

CLI options include `--username`, `--port`, `--parent-key-filename`, `--timeout`,
`--ssh-config`, `--known-hosts-source`, `--known-hosts-path` and `--ask-pass`.
For interactive parameter dictionaries, use the normal Session.connect keyword
names. Configure a custom trust path with `$.set(known_hosts_path="...")` on the
calling Session before connecting. Never disable host-key verification merely
to make a connection succeed.

```text
host1 [ops]> $.sudo(password=None)
host1 [root]> $.su("postgres", password=None)
host1 [postgres]> exit()
host1 [root]> exit()
host1 [ops]> exit()
local [user]>
```

Omitting an authentication password asks through getpass in a terminal. Use
`password=None` explicitly for passwordless authentication; nonterminal input
requires an explicit password argument rather than an invisible password read.
You can also set a variable with `password = getpass("Password: ")` in Python and reference it in an expression. Do not place real secrets in literal
commands or shared transcripts.

The displayed account is queried after entering the environment, not assumed
from the requested account. `:status` shows all environment layers. File
transfers retain the SSH connection account's permissions even inside sudo/su.
The console rejects connect() from explicit sudo/su/shell/program layers: leave
that layer first. Elevating a console does not change the Session's SSH
credentials or the account owning its SFTP/key-file reads.

## Text programs and interruption

Use explicit enter() for a program that asks questions or provides a REPL:

```text
local [user]> $.enter("python3 -q -u", prompt=">>>")
local [?] program> print(6 * 7)
42
local [?] program> $.exit("quit()")
local [user]>
```

Configure the program's actual readiness prompt. The exit sequence can be supplied
when leaving with `$.exit("quit()")`, or configured in advance with
`$.enter(..., exit="quit()")`. Bare `exit`, `exit()` and `$.exit()` use that
configured sequence. Without a sequence, they display a reminder and leave the
program open; they send neither Ctrl-C nor EOF. A supplied exit command is sent
once. The layer closes only after a detected return to its parent shell; if the
program continues or the read times out, the layer stays open and `poll()` can
observe a later return. Native program exit commands (for example MySQL `\q`)
can also return automatically. Bare `quit`/`quit()` remain whole-console controls. Plain input
in this layer goes to the program; `exit`, `exit()`, `quit`, `quit()`, lines
beginning with `$.` and the colon management commands remain reserved. Use
`$.input(...)` or `$.send(...)` to send text that would otherwise be interpreted as a management expression.
Ctrl-C/Ctrl-D go to the entered program. In particular, Ctrl-D in an entered
Python REPL exits that REPL and restores the SSHScript prompt, rather than
closing the entire SSHScript console. Outside enter(), Ctrl-C requests managed
shell cancellation or interrupts Python code. An interrupted Python multiline
input is discarded. A failed/unusable channel
is removed from the environment stack; the console never silently reconnects
and claims that the previous state survived. At the Python prompt, use
`exit` or `exit()` to leave a layer. If a text program returns to its parent
shell and that return is detected, its program layer is closed automatically.

This console supports text commands and explicitly configured text programs,
not full-screen applications or transparent terminal passthrough. Dollar shell
commands do not automatically detect interactive programs; use enter() for them.
Command results retain up to 8 MiB per stream; reaching that capture limit is
reported and the displayed stream may omit output. PTY stdout/stderr can merge.
Readiness or silence is not interpreted as a successful process exit.

## Hidden program input (7.0)

In the terminal console, recognized prompts such as `Enter password:`,
`Password for user:`, `Enter passphrase for key ...:`, PIN/token prompts and
common Chinese password prompts use hidden input for the next reply. Input
then returns to the normal reader. Detection checks the current output tail
before reading a new line, including prompts split across output chunks and
ANSI-colored prompts. It is a heuristic: an unfamiliar or late-arriving prompt
may not be recognized, and an already active normal input read cannot switch
retroactively. For those cases, enter this control expression instead of the
secret itself:

```python
$.input(secret=True)
```

It reads one hidden line and sends it directly to the current enter() program,
without evaluating Python/dollar syntax or adding the secret to readline history.
The operation returns None. It is console-only and requires an entered program.
`$.input("reply")` keeps its existing line-input behavior. For SSH credentials,
use `$.connect("user@host", password=getpass("SSH password: "))`.
Use `getpass()` inside an argument or assignment: a bare `getpass()` expression
returns a string that the Python REPL displays. Use `$.input(secret=True)` for a
program reply instead.

No characters or asterisks are displayed. If the terminal cannot disable echo,
input fails rather than falling back to plaintext. Ctrl-C/EOF restore the local
terminal settings; no completed secret line is sent when reading is cancelled.
The receiving program must also disable its own echo: remote output is displayed
as received, without automatic secret redaction. Do not put literal secrets in
Python expressions, print them, or ask an untrusted program to echo them.

## Stop a script, leave a layer, or quit

- `$.stop(code=0, message="")` normally completes the nearest script execution.
  It is unavailable at the console prompt itself.
- Bare `exit`, `exit()` and `$.exit()` leave one managed interactive layer. At the local
  root they close the console. These are console helpers, not script APIs.
- Bare `help` or `help()` displays console instructions; `help(object)` retains
  Python's object documentation behavior.
- Bare `quit` and `quit()` close every managed layer. Calling `exit()` or
  `quit()` unwinds the current Python cell, including `finally`/lexical contexts,
  before performing the requested cleanup.
- Ctrl-C at a Python prompt discards the pending input. During Python execution
  it interrupts that code; during a shell command it requests managed cancellation.
  Variables and usable environments remain available afterward.
- Ctrl-D/EOF at the Python prompt closes all layers, like quit(). In a terminal,
  EOF is produced by Ctrl-D on an empty input line; partial-line behavior follows
  the terminal's normal line editing.
- In an enter() program, Ctrl-C/Ctrl-D are forwarded as raw terminal control
  characters, without an added newline. Only a detected return to the parent
  shell closes that program layer; the Python console stays available.
- Use `help`/`help()` and `quit`/`quit()`. The former `:help` and `:quit` aliases
  are removed; `:status` shows the environment stack.
  The Python helper names can be shadowed by assignment, just like Python names;
  the colon aliases and `control.quit()` remain available.
- Python `sys.exit()` retains SystemExit semantics. The interactive boundary
  catches it, reports its status and keeps the console open.

The console intentionally gives `exit` and `exit()` the same one-layer behavior.
Use `quit` or `quit()` for all layers, and `$.stop()` for normal script
completion. `$.exit()` is available only at the console prompt; it is not a script API.

`script_result = $.run(source)` executes in the current connection Session; it
does not inherit an elevated console as its command target. `$.run_file(path)` uses the public
file runner, which creates a fresh local Session. A stopped script returns to
the console. Assign its returned ScriptResult to inspect completion and names;
script results do not automatically replace the console's Python namespace.
`with` and `finally` still perform cleanup on early completion.

`Session.run()` and `run_script()` return ScriptResult, a dictionary of executed
names with `.exitcode`, `.stopped` and `.message` attributes. `run_file()` returns
the integer completion status. A stopped imported `.spy` module keeps the names
initialized before stop(), and its importer continues normally. Cleanup failures
remain errors even if the script requested normal completion.

## Incompatible changes from 5.0.0

Replace `$.break(...)` with `$.stop(...)`. Replace script-ending `$.exit(...)`
with `$.stop(...)` for normal completion, or Python `sys.exit(...)` when the
caller should receive SystemExit. The old Break/Exit exception classes and the
old direct wrapper exit behavior are removed. `Session.exit()` and wrapper
`.exit()` remain unavailable. In the console, use `exit`, `exit()` or `$.exit()`
to leave one managed layer; use `$.exit("command")` to supply a program exit
sequence when leaving. In scripts, let Python manage lexical
`with` blocks. The earlier preview's bare-exit reminder and whole-console
`exit()` behavior are replaced by this one-layer rule.

The initial shell-first preview's `:python` and `:shell` commands are removed.
Input now follows Python/dollar syntax throughout; prefix shell commands with `$`.

Type `help` for a reminder. Operation failures display their type without
reprinting credential-bearing input. Use `:error` to display the original error
message, or `:traceback` for the full traceback. Both commands work inside entered
programs and are never sent to the program. Details are displayed only on request
and may include values from the original exception. `print(error)` is also
available at the Python prompt, but inside enter() plain text goes to the program.

Entered programs do not require `prompt=` to retain output or detect a return to
the parent shell. Output received during an input timeout is still displayed;
pending output is drained before another reply replaces the capture buffers.
A late parent-shell return is checked before sending another program reply.
Use `prompt="mysql>"` if you also want explicit MySQL readiness detection.
Do not add a newline to `$.exit("quit")`; one is supplied automatically.

*Last modified: 2026-10-30 00:10:17*
