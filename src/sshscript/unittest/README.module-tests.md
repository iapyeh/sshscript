# Credential-free module tests

`test_sshscript_module.py` verifies SSHScript's regular Python module API, and
`test_spy_thread_session.py` verifies `.spy` thread Session inheritance. They
do not connect to an SSH server, read a private key, or require a username or
password. Command tests use local subprocesses; SSH Session inheritance uses
connected in-memory test doubles.

Run the suite from the source directory:

```sh
python3 -m unittest discover -v -s unittest -p 'test_*.py'
```

The suite uses only Python's standard `unittest` framework in addition to
SSHScript's normal runtime dependencies, so no separate test package is
required. It covers:

- import-time isolation for process hooks, warnings, logging, and threads;
- explicit, reversible `.spy` imports through `sshscript.spy_imports()`;
- importing and constructing the public `Session` class;
- side-effect-free construction and scoped session-stack activation;
- the initial state and lifecycle of a credential-free local session;
- direct command strings assembled with `shlex.join()`, stdin, environment
  variables, stdout, stderr, and exit codes;
- automatic and explicit shell selection through `Session.exec_command()`;
- invalid command arguments and repeatable cleanup;
- execution of ordinary Python through `run_script()`;
- single-file execution and input validation through `run_file()`;
- independent local sessions running concurrently in worker threads; and
- connected Session inheritance in `.spy` threads, including concurrent nested
  connections, using in-memory SSH clients instead of credentials or a network.

The command exits with a nonzero status and prints the failing assertion if a
behavior does not match the installed source.

## Transport and cleanup boundaries

SSHScript is an execution layer for humans and AI. These regressions verify
observable execution contracts: exact input, retained output, failure versus
completion, deadline/cancellation, and resource ownership. They do not prove an
application's deployment succeeded or that closing an SSH channel killed its
remote process.

Run the focused checks from the source directory (Python 3.11+):

```sh
python3 -m unittest discover -v -s unittest -p 'test_command_job.py'
python3 -O -m unittest discover -v -s unittest -p 'test_command_job.py'
python3 -m unittest discover -v -s unittest -p 'test_stdin_contract.py'
python3 -m unittest discover -v -s unittest -p 'test_ssh_security.py'
```

The Paramiko socketpair fixture now forwards stdin to a real subprocess and
pumps stdout/stderr concurrently. A 32 KiB SSH window forces flow control.
The full-duplex test supplies more than 512 KiB of binary/Unicode input while
the child first emits 256 KiB on **each** output stream before reading input.
It compares complete output, input SHA-256, byte count and EOF on local and SSH
backends, using legacy calls, managed calls and `start()`. Empty input has its
own bounded EOF test. Failure to progress is a test failure, not a skip.

Other assertions cover:

- missing SSH exit status raises EOFError, never a fabricated completed result;
- transport loss after observed output preserves job output, propagates a
  transport error (not a command deadline), and forbids local execution fallback;
- losing one channel does not close a usable shared transport;
- three cycles per backend of completion, cancellation and timeout release owned
  I/O/watch threads, local processes/pipes and SSH channels;
- final fixture cleanup joins transport/server workers and checks descriptor
  counts on systems exposing `/proc/self/fd` or `/dev/fd`.

Server-side fixture cleanup explicitly kills surviving test processes. That is
fixture housekeeping, not evidence that SSH channel cancellation killed them.
Remote non-PTY stop remains `termination_status="unknown"`; local owned-process
stop has confirmed status. These are bounded regressions, not a long-term soak
or every possible server/network failure.

## Real OpenSSH and dependency evidence

The disposable CI server permits local TCP forwarding only to its own loopback
SSH endpoint for nested SSH and ProxyJump checks. Other destinations and remote
listeners remain prohibited; the integration suite verifies that restriction.

`test_openssh_integration.py` also exercises more than 4 MiB of input with
3 MiB on each output stream before input is read, EOF, execution-time transport
loss, nested SSH, and ProxyJump with strict host-key checks. It verifies nested
child closure preserves its parent, and proxy process/streams/transport threads
are released. An unknown jump-host key must reject the connection.

On a disposable Linux runner with passwordless sudo, provision the existing
loopback fixture; do not provision test accounts on a production machine:

```sh
bash tools/setup_openssh_ci.sh /tmp/sshscript-test.env
set -a
. /tmp/sshscript-test.env
set +a
python3 -m unittest discover -v -s unittest -p 'test_openssh_integration.py'
```

The CI job installs the verified wheel and runs these tests outside the source
checkout using `python -I`. CI and release jobs select Paramiko 2.11.0 (the
metadata minimum) with Python 3.11 and 3.14, a current 3.x on Python 3.11, and a
current 4.x on Python 3.14. Source/sdist checks cover the selected dependencies;
release jobs test the same built wheel with those dependencies. Version and
exception details remain in the job logs. The default Linux/macOS Python matrix
continues to cover 3.11–3.14.

An unconfigured native test is skipped and is not evidence of a pass. A CI
matrix definition is not evidence that CI ran: report source, socketpair, native
OpenSSH, installed-artifact and remote CI results separately. This coverage
also does not replace the native PAM/su/sudo matrix in
[the authentication test guide](README.console-authentication.md).
