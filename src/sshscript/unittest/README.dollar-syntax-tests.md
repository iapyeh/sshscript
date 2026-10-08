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
- string/argv command validation, three-value results, and explicit shell options;
- dollar commands inside Python functions;
- a persistent local shell created with `with $(...)`; and
- direct import of another `.spy` module containing dollar syntax.

## Local language regression suite

Run the 13 credential-free language cases with:

```sh
python3 sshscript.py unittest/language_fixture.spy
```

This suite also serves as the `.spy` import fixture. It contains no remote
host setup, private-key paths, SSH-agent use, or private settings imports.

## Files included in public validation

Only the reviewed regression files listed in `tools/prepare_release.py`
are included in release preparation and source archives. The legacy
`unittest-v3/` directory and environment-specific exploratory scripts are
private and excluded from Git tracking. New test files are ignored until
their paths and purpose have been explicitly approved for tracking.
