# SSHScript

## index

- [Tutorial](https://iapyeh.github.io/sshscript/tutorial){:target="_blank"}
- [Syntax](https://iapyeh.github.io/sshscript/syntax){:target="_blank"}
- [CLI](https://iapyeh.github.io/sshscript/cli){:target="_blank"}
- [Module](https://iapyeh.github.io/sshscript/module){:target="_blank"}

## Introduction

The sshscript let you embed shell commands in python script. It is like writing shell-script in python. Below is an example. It makes ssh connection to the host1, then from the host1 makes connection to the host2. Then It executes “netstat -antu” on the host2.

```python
$.connect('username1@host1')
$.connect('username2@host2')
$netstat -antu

```

Or, be explicitly

```python
with $.connect('username1@host1') as _:
    with $.connect('username2@host2') as _:
        $netstat -antu
```

If you did not “ssh-copy-id” to the host1 and host2, then just do it like this:

```python
$.connect('username1@host1', password='secret')
```

Doing nested-scp is simple too. The script below downloads the /var/log/message from the host2 and uploads config.ini on the [localhost](http://localhost) to  /tmp on the host2.

```python
with $.connect('username1@host1') as _:
    with $.connect('username2@host2') as _:
        $.download('/var/log/message')
        $.upload('config.ini','/tmp')
```

Your script is full-powered by the Python.

```python
# This script would ssh to a remote server.
# Then print out all its IP addresses.

# Below is regular python script
from getpass import getpass
password = getpass()

# Below is sshscript-style syntax
# First: ssh to username@host with password
$.connect('username@host',password=password)
# Second: execute command "ifconfig | grep inet"
$ifconfig | grep inet
# Third: collect the output
conten = $.stdout
# Close the connection, not required but good boys always do.
$.close()

# Below is regular python script
def remove_control_characters(s):
    global unicodedata,re
    s = re.sub(r'[\x00-\x1f\x7f-\x9f]', '',s)
    s = re.sub(r'\[.*?[a-zA-Z]', '',s)
    return s
myIp = set()
for line in content.split('\n'):
    line = line.strip()
    line = remove_control_characters(line)
    if line.startswith('inet'):
        cols = line.split()
        if cols[0] == 'inet':
            ip = cols[1].split(':')[-1]
            myIp.add(ip)

print(myIp)
```

The sshscript is based on subprocess and [Paramiko](https://www.paramiko.org/). You can embed commands to run and get its output on localhost. As well as, you can embed commands to run and get its output on remote host.

## Installation

```python
pip install sshscript
```
