---
title: "How .spy Transformation Works"
parent: "Concepts"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 4
permalink: /v3a/concepts/how-spy-transformation-works/
---

# How .spy Transformation Works

SSHScript does not teach Python's parser to understand `$command` directly. It
converts Dollar syntax into a Python abstract syntax tree, compiles that tree
with original source locations, and executes it with an active Session context.

Application code should depend on documented Dollar behavior, not on the exact
generated Python.

## Transformation pipeline

For source containing Dollar syntax, SSHScript:

1. caches the original source for diagnostics;
2. tokenizes it and replaces recognized Dollar forms with Python-compatible
   placeholders;
3. parses the placeholder source into a Python AST;
4. rewrites placeholders into operations on the active Session or console;
5. repairs AST locations and compiles with the original filename; and
6. executes while the selected Session is active.

The token stage is lexical. Dollar characters inside ordinary Python strings
and comments remain data:

```python
literal = "$.stdout $hostname $$hostname"
raw_literal = r"$HOME and $.stderr"
```

## How runners choose the pipeline

`Session.run()`, `run_script()`, and `run_file()` first try to parse the source
as ordinary Python. If that succeeds, they compile it normally. If parsing
raises `SyntaxError`, they attempt Dollar transformation.

The filename extension alone therefore does not force transformation through
`run_file()`. A syntactically valid `.spy` file can execute as ordinary Python.

The explicit `.spy` importer behaves differently: a discovered `module.spy` or
`package/__init__.spy` is compiled through the `.spy` pipeline. These are
current v3.1.4 selection rules, not a recommended business-logic test.

## Conceptual lowering

Given:

```python
$hostname
print($.stdout.strip())

command = "printf ready"
$(command, shell=False)

with $.connect("ops@example.net"):
    $uname -s
```

the supported mental model is:

- `$hostname` calls `exec_command("hostname")` on the active context;
- `$.stdout` reads the latest result from that context;
- `$(command, shell=False)` forwards the expression and options to
  `exec_command()`; and
- `with $.connect(...):` obtains a child and makes it active for the block.

Inside `$.shell()`, `$.sudo()`, `$.su()`, or `$.enter()`, Dollar commands
resolve to the active console.

Temporary identifiers, placeholders, and the exact generated statements are
implementation details.

## Active context resolution

Each transformed execution uses a per-thread context stack. The top item is the
active Session or console:

```text
local Session
└── remote Session created by $.connect()
    └── persistent shell or interactive console
```

Entering a scope pushes a context; leaving restores the previous item.
`Session.run()` activates its Session only for the duration of that call.

A scoped connection is preferred:

```python
with $.connect("ops@example.net"):
    $hostname
```

An unscoped `$.connect(...)` currently becomes explicit stack activation and
stays active until closed. This compatibility behavior is harder to reason
about and should not be the default style for new code.

## Source locations and tracebacks

Generated AST nodes are anchored to their originating `.spy` nodes, and the
original source is registered with Python's `linecache`.

The v3.1.4 regression suite covers diagnostics for:

- ordinary Python runtime errors inside `.spy` source;
- failures on a Dollar command;
- nested `$f'...'` expressions;
- inner lines of multiline `$(...)`;
- ordinary syntax and tokenization errors;
- unmatched delimiters and transformer failures; and
- imported `.spy` modules.

These cases retain the original filename, source line, and tested line number.
Transformer failures are presented as source-located `SyntaxError` instances
while preserving the internal cause.

This is source-oriented error mapping, not a guarantee of a particular
character-for-character source-map format for every future Python grammar
construct.

## Inspect generated Python

Display transformed Python without executing it:

```sh
sshscript --script automation.spy
```

Programmatic runners accept `showScript=True` as well. The display uses
`ast.unparse()` and is useful for inspection, but:

- formatting can differ from the original source;
- it is not the source map used by tracebacks;
- generated names and lowering details are not stable public API; and
- application code must not parse or depend on the display.

## Import `.spy` modules explicitly

Importing `sshscript` alone does not install a process-wide import hook:

```python
import sshscript
from sshscript import Session


session = Session()
try:
    with session:
        with sshscript.spy_imports():
            import automation

        automation.run()
except BaseException as primary:
    if not session.close():
        primary.add_note("SSHScript cleanup also failed")
    raise
else:
    session.close(strict=True)
```

The context is reference-counted, nestable, and reversible. It supports
`module.spy`, packages with `__init__.spy`, and relative imports.

`run_file()` enables the importer while its selected script runs, so `.spy`
modules can import one another without leaving the finder installed globally.
Imported modules remain cached in `sys.modules` normally.

A module that executes Dollar commands during import needs an active Session.
Keeping import and calls inside an explicit Session scope makes that dependency
visible.

## Thread construction in transformed source

The AST pass recognizes normal aliases of:

- `threading.Thread(...)`; and
- `Thread(...)` imported from `threading`.

It redirects those calls through a context-aware factory. The result is still a
standard `threading.Thread`; SSHScript does not globally replace the class or
add application-visible context attributes.

```python
import threading


def worker():
    $hostname
    print($.stdout.strip())


with $.connect("ops@example.net"):
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
```

The active stack is snapshotted when the Thread is constructed. It contains
references to the same Session objects, not cloned connections. Keep the
owning scope alive until every worker joins and avoid concurrent mutation of
one Session's latest result.

Dynamic factories and aliases the transformer cannot recognize are not
rewritten. Ordinary `.py` files are not transformed, so their threads do not
inherit a context automatically.

## Execution namespaces

`Session.run(source, vars=...)` executes with a new dictionary copied from the
supplied mapping. New assignments do not modify the original mapping, while
referenced mutable objects remain shared.

`run_file()` also supplies `__name__ = "__main__"` and `__file__`, temporarily
adds the script directory to `sys.path`, and uses a fresh local Session that it
closes afterward.

Continue with the [Dollar Syntax Tutorial](../../tutorials/dollar-syntax/) or
the [Session Lifecycle](../session-lifecycle/) concept.

Last Updated: 2026-09-25 16:37:52
