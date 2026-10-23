# Unified Console API

**Contract: SSHScript 6.1.0; Python 3.11+.**

Design and lifecycle contract, written before implementation.

`from sshscript import Console` exposes the shared Python/dollar console
on an existing `Session`. `Console(session, ownership="borrowed")` opens only a
new Bash channel, without connect(), authentication or Session settings changes.
Jump connections and SSH/SFTP login identity remain owned by the caller.
`ownership="owned"` explicitly transfers the supplied Session (and its children,
not its ancestors) to the console. Ownership begins at construction, including
initialization failure. A local Session is also supported.

All calls run on the constructing thread. The caller must serialize console and
Session use until close. Python evaluation and lexical with blocks are synchronous;
arbitrary Python cannot be safely preempted. `submit(line)` retains the existing
compiler and namespace. `start_command(command, timeout=60)` starts the existing
persistent-shell foreground job; `poll()` reads incremental output without waiting.
`send_input(text, timeout=...)` replies to an enter() program, appending one newline.
`send_input(text, newline=False)` sends raw text to an enter() program.
Shell jobs reject stdin writes: a late write could reach the parent shell after
the process exits. Use enter() for interactive applications.
`interrupt()` stops a job with bounded recovery, or sends Ctrl-C to a program;
otherwise it discards unfinished Python input. After program Ctrl-C, a matched
program prompt returns `waiting_input` and remains ready across polls, even when
the protocol has consumed the prompt text. A control-read timeout stays `running`;
a later prompt can restore readiness through `poll()`. `error_type=KeyboardInterrupt`
records the interruption attempt, not program completion or failure. If the program
exits, its restored exit status determines `completed` or `failed`. `eof()` leaves program EOF behavior
unchanged; at the Python prompt it closes the console. `leave()` exits one layer,
including the root shell; `close()` unwinds everything. `quit` closes everything.
Python SystemExit is reported as failed input and leaves the console open.
A host exception in `with Console(...)` runs cleanup; cleanup failure is never
suppressed. Initialization failure cleans up the acquired channel.

Immutable `ConsoleUpdate` records carry state, incremental stdout/stderr, a command result,
safe error type, and Session reuse status. States are `ready`, `incomplete`,
`running`, `waiting_input`, `completed`, `failed`, `closed`. A nonzero exit status,
Python/syntax error, deadline expiry or unconfirmed recovery is failure. `completed`
requires a real job completion record or a restored program exit status, never silence. `waiting_input` means an
enter() prompt matched the configured program protocol; it is not proof of command
success. Silent or timed-out interactive reads remain `running`. A generic process
cannot reveal whether it is waiting for stdin: shell jobs remain `running` until
completion. Polling does not infer readiness from text.
For an ordinary Python cell, completed means evaluation returned without an
uncaught exception. It does not certify side effects or results of arbitrary
Python calls. The exit-status classification applies to managed dollar jobs,
start_command() and restored enter() program results; inspect other returned
Python API results explicitly. Configure enter() prompts
for text programs; full-screen terminal emulation is unsupported.

`connection` returns the current Session, without changing its login account.
`environments` returns immutable snapshots with kind, host, connection username,
effective username and identity verification. Effective names come from `id -un`
on entry; program layers inherit the last verified name with verification false.
They are observations, not authorization evidence for subsequent arbitrary Python.
Leaving a nested layer restores its parent channel; closing the root channel does
not attempt to preserve that shell's cwd/environment in the Session's later new
commands. A successful borrowed close additionally probes Session command execution
with a finite budget; `session_reuse="confirmed"` means cleanup and that probe
succeeded. `unknown` means the caller must reconcile or discard the connection;
`closed` means an owned Session was closed. No API can guarantee future network
availability or remote child-process termination from a channel close alone.

`credential_resolver(SwitchRequest)` runs before every managed su/sudo switch,
including explicit credentials. It may reject by raising or return
`SwitchCredentials(password=...)`; None keeps explicit credentials. Request metadata
contains no password. `switch_observer(SwitchOutcome)` receives success/failure,
request, resulting environment and safe error type, never credential/error text.
The resolver implements host configuration, candidate ordering and policy outside
SSHScript. It is called once per attempted switch; there is no automatic retry.
A missing password in non-terminal mode raises `CredentialsRequiredError`;
explicit None requests passwordless authentication. Observer failure propagates;
a successful switch remains active and is visible for cleanup. Explicit password
arguments and arbitrary Python error objects are sensitive application memory.
Do not log input source, namespace/error objects, JobResult.command or arbitrary
program output containing secrets. Use the resolver rather than literals in input.
Hooks cover managed Console.su/sudo and prompt-level dollar calls; arbitrary Python,
raw Session access and lexical script with blocks are trusted code, not a policy
sandbox. Hosts must restrict supplied code if they need enforced authorization.

`terminal=False` needs no terminal on the Python process. The new shell still uses
a PTY by default for su/sudo and reliable job interruption. `get_pty=False` supports
pipe jobs but cannot safely interrupt a running job; recovery can be unknown.
Programs/password readers may require a PTY. No hidden getpass prompt is used in
non-terminal mode. `terminal=True` enables the terminal frontend of the same Console core
and getpass fallback. Captured event streams and terminal streams are separate;
headless capture is consumed by each returned update. When a custom stdout or
stderr stream is supplied (or terminal=True selects terminal streams), that
stream receives the output and the corresponding update output field is empty. Only one console/redirected
Python execution may run in a process at a time because Python stdout redirection
is process-global. This API does not provide a Python sandbox or an async Python
executor.

## One core for CLI and host integration

The CLI and embedding applications use the same public `Console` implementation
in `interactive.py`. There is no legacy InteractiveConsole class, separate embedded
subclass, or compatibility module. The CLI creates an explicit owned local Session;
embedding callers normally borrow the Session they already hold. Both frontends
use submit(), poll(), interrupt(), eof() and the same cleanup and failure policy.
The CLI drains foreground $.start() jobs through poll() before reading another line.

Earlier 6.0 CLI behavior is not a compatibility target. Internal open()/execute()
entry points are removed: construct Console(session) and call submit(line).
`:help` and `:quit` aliases are removed; use help/help() and quit/quit(). `:status`
remains the environment-stack command. Diagnostics always omit source and arbitrary
exception text, including NameError and SystemExit values. A failed channel remains
owned until cleanup and is reported as unknown; it is not silently popped to an
apparently healthy parent layer. SSH/SFTP authentication and Session command APIs
keep their existing responsibilities.

This public API is released in SSHScript 6.1.0. During development, minor releases
may include incompatible changes; compatibility is required only when explicitly
requested. Pin the released artifact or record the exact source revision/hash.

## Executable examples

Run from the flat source checkout with `PYTHONPATH=. python3 -B` followed by
[examples/embedded_agent.py](examples/embedded_agent.py) or
[examples/embedded_terminal.py](examples/embedded_terminal.py). With the matching
installed wheel the PYTHONPATH setting is unnecessary. Both examples create only
local Sessions; `handover(existing_target)` and `drive(existing_target)` also
accept a host's already-connected target Session, including a jump target.

Terminal handover, followed by reuse:

```python
from sshscript import Console

def handover(existing_target):
    with Console(existing_target, terminal=True) as console:
        console.interact()
    assert console.session_reuse == "confirmed"
    return existing_target.exec_command("hostname", check=True)
```

Non-terminal Python/dollar cells and asynchronous shell output:

```python
import time
from sshscript import Console

def drive(existing_target):
    with Console(existing_target) as console:
        assert console.submit("value = 42").state == "completed"
        assert console.submit("$export TASK=value; cd /tmp").state == "completed"
        update = console.start_command('printf "%s" "$TASK"', timeout=3)
        while True:
            consume(update.stdout, update.stderr)  # host callback
            if update.state != "running":
                break
            time.sleep(.03)
            update = console.poll()
        if update.state != "completed":
            raise RuntimeError("command failed: " + str(update.error_type))
        assert update.result.exitcode == 0
    return existing_target.exec_command("printf reusable", check=True)
```

For a text program, call `console.enter("python3 -q -u", prompt=">>>", exit="quit()")`,
then `console.send_input("print(42)", timeout=2)`. A prompt response produces
`waiting_input`; program exit restores the parent and supplies `result.exitcode`.
`poll()` can observe a program's later prompt/exit after a timed-out read or raw
send. Program results snapshot the final input buffers; retain incremental events
for the full conversation. Job results snapshot the bounded whole command output.
`poll()` may perform bounded shell recovery when an enter() program has exited;
it does not block on a running shell job. Program restoration uses the existing
console exit budget (up to 60 seconds), unlike immediate job polling.

Credential and policy integration (no host configuration parser in SSHScript):

```python
from sshscript import Console, SwitchCredentials

def resolve(request):
    host_policy.require_switch(request.environment.host, request.kind, request.username)
    # Return None only when keeping an explicit password argument. Returning a
    # SwitchCredentials object with password=None deliberately tries passwordless.
    return SwitchCredentials(secret_store.password_for(request.username))

with Console(existing_target, credential_resolver=resolve,
             switch_observer=audit_switch_metadata) as console:
    console.su("operator")
    print(console.environments[-1])
    console.leave()
```

The host supplies `consume`, `host_policy`, `secret_store` and
`audit_switch_metadata`; the linked executable examples need none of these.
Resolver/observer exceptions from direct method calls propagate. `submit()` reports
safe error types instead. Cleanup errors always raise `ConsoleCleanupError` with
`session_reuse="unknown"`; repeated close reports the same failure. Initialization
raises `ConsoleInitializationError` with unknown reuse, even if channel cleanup
appeared successful. If the host body and cleanup both fail, both errors are
preserved in a BaseExceptionGroup. Do not reuse an unknown Session on the strength
of a prompt or a successful command from an unrelated shell.

*Last modified: 2026-10-23 18:39:31*
