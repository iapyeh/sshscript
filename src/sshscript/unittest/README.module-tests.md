# Credential-free module tests

`test_sshscript_module.py` verifies SSHScript's regular Python module API. It
does not use SSHScript's dollar syntax and does not connect to an SSH server,
read a private key, or require a username or password. Every command is run as
a local subprocess.

Run the suite from the source directory:

```sh
python3 -m unittest discover -v -s unittest -p 'test_sshscript_module.py'
```

The suite uses only Python's standard `unittest` framework in addition to
SSHScript's normal runtime dependencies, so no separate test package is
required. It covers:

- importing and constructing the public `Session` class;
- the initial state and lifecycle of a credential-free local session;
- structured command arguments, stdin, environment variables, stdout, stderr,
  and exit codes;
- automatic and explicit shell selection through `Session.exec_command()`;
- invalid command arguments and repeatable cleanup;
- execution of ordinary Python through `run_script()`;
- sorted multi-file execution and explicit exports through `run_file()`; and
- independent local sessions running concurrently in worker threads.

The command exits with a nonzero status and prints the failing assertion if a
behavior does not match the installed source.
