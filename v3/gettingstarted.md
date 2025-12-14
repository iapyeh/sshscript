# Getting Started with SSHScript

SSHScript is a Python library that simplifies SSH interactions, allowing you to write shell scripts in Python with enhanced control and readability. This guide will walk you through the basics of setting up and using SSHScript.

## Installation

First, you need to install SSHScript. You can do this using pip:

```bash
pip install sshscript
```

## Basic Usage

Let's start with a simple example. We'll connect to a remote server, execute a command, and print the output.

```python
from sshscript import Session

# Create a new SSH session
# Replace 'user', 'password', and 'your_server_ip' with your actual credentials and server IP
with Session('user@your_server_ip', password='your_password') as session:
    # Execute a command on the remote server
    result = session.run('ls -l /')

    # Print the standard output and standard error
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)

    # You can also access the exit code
    print(f"Exit Code: {result.exit_code}")
```

### Running Multiple Commands

You can run multiple commands sequentially within the same session:

```python
from sshscript import Session

with Session('user@your_server_ip', password='your_password') as session:
    session.run('mkdir my_test_directory')
    session.run('echo "Hello from SSHScript!" > my_test_directory/hello.txt')
    result = session.run('cat my_test_directory/hello.txt')
    print(result.stdout)
    session.run('rm -rf my_test_directory')
```

### Handling Errors

SSHScript allows you to easily check for command execution errors. By default, if a command returns a non-zero exit code, an `SSHScriptError` will be raised.
