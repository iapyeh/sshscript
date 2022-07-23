# SSHScript Documents

- [Tutorial](https://iapyeh.github.io/sshscript/tutorial) 
- [Syntax, Variables and Functions](https://iapyeh.github.io/sshscript/syntax)
- [sshscript CLI](https://iapyeh.github.io/sshscript/cli)
- [sshscript Module](https://iapyeh.github.io/sshscript/module) 
- [導覽(Tutorial in zh-TW)](https://iapyeh.github.io/sshscript/tutorial.zh-tw)

## Introduction

The sshscript let you embed shell commands in python script. It is like writing shell-script in python. Below is an example. It makes ssh connection to the host1, then from the host1 makes connection to the host2. Then It executes “netstat -antu” on the host2.

```python
$.connect('username1@host1')
$.connect('username2@host2')
$netstat -antu
```

Or, to be explicit,

```python
with $.connect('username1@host1') as _:
    with $.connect('username2@host2') as _:
        $netstat -antu
```

Put the three lines into a file, say “hello.spy”, then execute it on your console by

```bash
sshscript hello.spy
```

If you did not “ssh-copy-id” to the host1 and host2, then just give the password like this

```python
$.connect('username1@host1', password='secret')
```

Doing nested-scp is simple too. The script below downloads the /var/log/message from the host2 and uploads config.ini on the localhost to  /tmp on the host2.

```python
with $.connect('username1@host1') as _:
    with $.connect('username2@host2') as _:
        $.download('/var/log/message')
        $.upload('config.ini','/tmp')
```

Your script is full-powered by Python.

```python
# This script would ssh to a remote server.
# Then print out all its IP addresses.

#
# Below is regular python script
#
import unicodedata,re
from getpass import getpass
password = getpass()

#
# Below is python script with content of sshscript syntax
#
# First: ssh to username@host with password
$.connect('username@host',password=password)
# Second: execute command "ifconfig | grep inet"
$ifconfig | grep inet
# Third: collect the output
conten = $.stdout
# Close the connection, not required but my boss always hopes me to do.
$.close()

#
# Below is regular python script
#
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

The SSHScript is based on subprocess and [Paramiko](https://www.paramiko.org/). You can embed commands to run and get its output on localhost. As well as, you can embed commands to run and get its output on a remote host.

## Installation

```python
pip install sshscript
```

## Disclaimer

- Developing and testing on MacOS, Linux only.
- This project is still in the beta phase. I’d like to keep its interface stable, but subject to change without notice.
- Please use it at your own risk.
