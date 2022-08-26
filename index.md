# SSHScript Documents



#### v1.1.14 Released on 2022/8/24 [Release Notes](https://iapyeh.github.io/sshscript/release-v1.1.14)

## en

- [Tutorial](https://iapyeh.github.io/sshscript/tutorial) 
- [Learning SSHScript Chapter 1](https://iapyeh.github.io/sshscript/learn-chap01)
- [Learning SSHScript Chapter 2](https://iapyeh.github.io/sshscript/learn-chap02)
- [Syntax, Variables and Functions](https://iapyeh.github.io/sshscript/syntax)
- [sshscript CLI](https://iapyeh.github.io/sshscript/cli)
- [sshscript Module](https://iapyeh.github.io/sshscript/module) 
- [Ways to get a root’s console](https://iapyeh.github.io/sshscript/examples/root-console)
- [Do logging](https://iapyeh.github.io/sshscript/examples/logger)
- [Troubleshooting of installation](https://iapyeh.github.io/sshscript/sshscript-problem)

## zh-TW

- [導覽(Tutorial)](https://iapyeh.github.io/sshscript/tutorial.zh-tw)
- [使用SSHScript教學一(Learning SSHScript Chapter 1)](https://iapyeh.github.io/sshscript/learn-chap01.zh-tw)
- [使用SSHScript教學二(Learning SSHScript Chapter 2)](https://iapyeh.github.io/sshscript/learn-chap02.zh-tw)
- [安裝有問題](https://iapyeh.github.io/sshscript/sshscript-problem.zh-tw)

## Introduction

SSHScript makes Python become a scripting tool for system automation. Functionally, the SSHScript is something like the Ansible. Instead of writing descriptive YML files, just write Python scripts with the simplicity of Python and the power of all Python packages.

The sshscript let you embed shell commands in python script. It is like writing shell-script in python. 

Below is an example. It makes ssh connection to the host1, then from the host1 makes connection to the host2. Then It executes “netstat -antu” on the host2.

```
$.connect('username1@host1')
$.connect('username2@host2')
$netstat -antu
```

Or, to be explicit,

```
with $.connect('username1@host1') as _:
    with $.connect('username2@host2') as _:
        $netstat -antu
```

Put the three lines into a file, say “hello.spy”, then execute it on your console by

```
sshscript hello.spy
```

If you did not “ssh-copy-id” to the host1 and host2, then just give the password like this

```
$.connect('username1@host1', password='secret')
```

Doing nested-scp is simple too. The script below downloads the /var/log/message from the host2 and uploads config.ini on the localhost to  /tmp on the host2.

```
with $.connect('username1@host1') as _:
    with $.connect('username2@host2') as _:
        $.download('/var/log/message')
        $.upload('config.ini','/tmp')
```

Your script is full-powered by Python.

```
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


## Releases

The last version is 1.1.14 on 2022/8/24. [Release Notes](https://iapyeh.github.io/sshscript/release-v1.1.14)

## Installation

```
pip install sshscript
```
## Examples

- [Examples](https://iapyeh.github.io/sshscript/examples) 

## Why and Features

The idea is that many automation tasks are running commands and dealing with outputs on localhost and remote hosts. Among these scripts, there are many common routines. Eg. making ssh connections, execution and collecting data. That's where the SSHScript comes into play. The most charming part is that you could directly process the resulting data in Python. It then enables you to efficiently build complex data structures and processing flow with object-oriented approaches.

- Easy to script. If you know what commands to run and which host to ssh, then you can write your script. No extra stuff to learn.
- Embedding shell commands in Python scripts are intuitive and self-explaining. It is good for teamwork and maintenance.
- Handling execution output or exceptions with Python is easier than shell script.
- Your scripts are powered by tons of Python packages.
- SSHScript supports thread, aka jobs in parallel.

![image](https://user-images.githubusercontent.com/4695577/186846232-c4a0809d-d085-4b3c-9694-319c21146d40.png)


## Disclaimer

- Developing and testing on MacOS, Linux, Freebsd only. For Windows users, suggestion is to use the SSHScript in the "bash of Powershell" or the WSL.
- Please use it at your own risk.

[![Downloads](https://pepy.tech/badge/sshscript)](https://pepy.tech/project/sshscript)
