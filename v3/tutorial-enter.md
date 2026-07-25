# SSHScript v3.0 Interactive and Foreground Commands

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Execute interactive and foreground commands: $.enter()](#dollar-enter)

## 🔵 <a name="dollar-enter"></a>Execute interactive and foreground commands: $.enter()

In SSHScript v3.0, the `$.enter()` method is a powerful, unified tool for handling both interactive programs (like `mysql`, `python`) and foreground programs that produce continuous output (like `tcpdump`, `tail -f`).

The `$.enter()` context manager returns a console object that can be used to send input and can also be iterated over to read live output line-by-line.

### Example 1: Interactive Command (mysql)

This example executes `mysql`, waits for a password prompt, provides the password, and then sends SQL commands.

```python
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234') as host:
    with host.enter('mysql -uroot -p dbname', 'password', '1234', exit='quit') as mysql:
        mysql.input("ALTER USER 'root'@'localhost' IDENTIFIED BY 'MyN3wP4ssw0rd';")
        mysql.input('show slave status\G;')
        
        # The full output is available after commands are sent
        for line in mysql.stdout.splitlines():
            if ':' in line:
                key, value = [x.strip() for x in line.split(':')]
                print(f"{key}: {value}")
```

### Example 2: Foreground Command (tcpdump)

This example runs `tcpdump` and processes its output in real-time. The loop will continue until it is explicitly broken. The `with` block ensures `tcpdump` is properly terminated when the loop exits.

```python
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234') as host:
    with host.sudo('sudopass') as sudo:
        # $.enter() returns an iterable console object
        with sudo.enter('tcpdump -n -i eth0 port 80') as tcp_stream:
            print('Starting to capture traffic on port 80...')
            for line in tcp_stream:
                print(f"Captured: {line.strip()}")
                # Add a condition to stop capturing
                if '192.168.1.100' in line:
                    print("Found target IP. Stopping capture.")
                    break 
```

### Example 3: Interactive Python Shell

You can also interact with a Python shell, sending code and reading results.

```python
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote:
    with remote.enter('python3 -i', exit='quit()') as python_shell:
        python_shell.input("import os")
        python_shell.input("print(os.getcwd())")
        
        # Wait for the output to appear
        python_shell.expect('>>>') 
        
        # The output of the print statement will be in stdout
        # Note: Parsing interactive output can be complex.
        # The output includes prompts and command echoes.
        print(f"Python shell output:\n{python_shell.stdout}")
```

This new `$.enter()` simplifies scripts by removing the distinction between `$.enter` and `$.iterate`, providing a single, intuitive way to manage interactive and streaming processes.

Last Updated: 2026-07-25 16:59:40
