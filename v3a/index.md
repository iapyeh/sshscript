---
title: "SSHScript v3 Documents"
nav_order: 1
has_children: true
---

# SSHScript v3 Documents

## What is SSHScript?

SSHScript is a Python-based system automation tool for running CLI programs and shell commands on local or remote hosts. It adds a concise dollar syntax to Python and also provides a regular Python `Session` API. The same automation logic can run locally, over SSH, or through nested SSH connections, with command results available as standard output, standard error, and exit code.

```python
# Run on localhost
$hostname
print($.stdout.strip())

# Run the same command on a remote host
with $.connect("user@host"):
    $hostname
    print($.stdout.strip())
```

## Why SSHScript?

Backend, DevOps, and SRE work often involves repeating manual operations across Linux consoles and SSH sessions. Shell scripts keep system commands close to the way engineers run them by hand, while Python provides clearer data processing, exception handling, reusable functions, third-party packages, and threading.

SSHScript brings these strengths together. It removes much of the boilerplate required to work directly with `subprocess` and Paramiko, lets engineers preserve familiar and proven commands, and provides one interface for local execution, remote execution, nested connections, interactive programs, and privilege changes such as `sudo`. This makes automation scripts easier to read, extend, and maintain as a task grows.

## Installation

Install SSHScript from PyPI with Python 3:

```sh
python3 -m pip install sshscript
# or
pip3 install sshscript
```

## Upgrading

Upgrade an existing installation to the latest available version:

```sh
python3 -m pip install --upgrade sshscript
# or
pip3 install --upgrade sshscript
```

## Learning
* [Tutorial (zh-TW)](tutorial-v3.0.zh-tw)

## References

## Releases 

* [v3.0.a Release Notes]

### SSHScript v3.0.a is a major update focusing on simplicity and power. If you find any bugs or have any suggestions, you are welcome to post them on the `issues` page.
