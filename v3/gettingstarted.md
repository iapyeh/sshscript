# Getting Started with SSHScript

SSHScript is a Python library that simplifies SSH interactions, allowing you to write shell scripts in Python with enhanced control and readability. This guide will walk you through the basics of setting up and using SSHScript.

## Installation

First, you need to install SSHScript. You can do this using pip:

```bash
pip install sshscript
```

## Basic Usage - Local Session
Let's start with a simple example. We'll execute a command, and print the output on localhost.

```python
from sshscript import Session
# Create a new SSH session
session = Session()
# Execute a command on the remote server
session('ls -l /')

# Print the standard output and standard error
print("STDOUT:")
print(session.stdout)
print("STDERR:")
print(session.stderr)

# You can also access the exit code
print(f"Exit Code: {session.exitcode}")


# Execute next command
stdout,stderr = session('hostname')
print('hostname={stdout.strip()}')

```


## Basic Usage - Remote Session

We'll connect to a remote server, execute a command, and print the output.

```python
from sshscript import Session

# Create a new SSH session
# Replace 'user', 'password', and 'your_server_ip' with your actual credentials and server IP
account = 'user@192.168.0.100'
password = '12345678'
with Session().connect(account, password=password) as session:
    # Execute a command on the remote server
    session('ls -l /')

    # Print the standard output and standard error
    print("STDOUT:")
    print(session.stdout)
    print("STDERR:")
    print(session.stderr)

    # You can also access the exit code
    print(f"Exit Code: {session.exitcode}")

    # Execute next command
    stdout,stderr = session('hostname')
    print('remote hostname={stdout.strip()}')
```

## Basic Usage - Nested Remote Session

We'll connect to a nested remote server, execute a command, and print the output.

```python
from sshscript import Session

# Create a new SSH session
# Replace 'user', 'password', and 'your_server_ip' with your actual credentials and server IP
account1 = 'user@192.168.0.100'
password1 = '12345678'
account2 = 'user@192.168.100.100'
password2 = '12345678'
with Session().connect(account1, password=password1) as session1:
    with session1.connect(account2, password=password2) as session2:
        # Execute a command on the remote server
        session2('ls -l /')

        # Print the standard output and standard error
        print("STDOUT:")
        print(session2.stdout)
        print("STDERR:")
        print(session2.stderr)

        # You can also access the exit code
        print(f"Exit Code: {session2.exitcode}")

        # Execute next command
        stdout,stderr = session2('hostname')
        print('remote hostname={stdout.strip()}')
```

Next: connection with private key
Next: multiple connections iterately