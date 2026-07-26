# Credential-free dollar syntax tests

`dollar_syntax.spy` is a localhost-only smoke suite for SSHScript's dollar
syntax. It does not load `localsecret.py` or `secret.py`, connect to an SSH
server, use an SSH agent, or read a private key.

Run the dollar syntax suite directly from the source directory:

```sh
python3 sshscript.py unittest/dollar_syntax.spy
```

It can also run through Python's standard `unittest` discovery. The wrapper
starts the `.spy` suite in an isolated subprocess with an empty temporary home
directory and SSH-agent variables removed:

```sh
python3 -m unittest discover -v -s unittest \
  -p 'test_sshscript_dollar_syntax.py'
```

Run both the module API and dollar syntax suites with:

```sh
python3 -m unittest discover -v -s unittest -p 'test_sshscript_*.py'
```

The dollar syntax suite covers:

- bare, string, raw-string, expression, and f-string command forms;
- assignment from a dollar command and result access through `$.stdout`,
  `$.stderr`, and `$.exitcode`;
- automatic shell selection for pipelines, assignments, logical operators,
  expansion, and redirection;
- string-only command validation and explicit `shell=False` or `shell=True`;
- dollar commands inside Python functions;
- a persistent local shell created with `with $(...)`; and
- direct import of another `.spy` module containing dollar syntax.
