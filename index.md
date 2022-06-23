# SSHScript

## index

- [Tutorial](https://iapyeh.github.io/sshscript/tutorial){:target="_blank"}
- [Syntax](https://iapyeh.github.io/sshscript/syntax){:target="_blank"}
- [CLI](https://iapyeh.github.io/sshscript/cli){:target="_blank"}
- [Module](https://iapyeh.github.io/sshscript/module){:target="_blank"}

## Introduction

The sshscript let you embed shell commands in python script. It is like writing shell-script in python. For example

```python
# This script would ssh to a remote server.
# Then print out all its IP addresses.

# below is regular python script
from getpass import getpass
password = getpass()

# below is sshscript-style syntax
# first: ssh to username@host with password
$.open('username@host',password=password)
# second: execute command "ifconfig | grep inet"
$ifconfig | grep inet
# third: collect the output
conten = $.stdout
# close the connection, not required but good boys always do.
$.close()

# below is regular python script
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
            myIp.append(ip)

print(myIp)
```

The sshscript is based on subprocess and [Paramiko](https://www.paramiko.org/). You can embed commands to run and get its output on localhost. As well as, you can embed commands to run and get its output on remote host.

## Installation

```python
pip install sshscript
```
