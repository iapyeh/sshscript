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

System automation is a process of realizing management logics by repeating networking and execution. SSHScript makes Python an easy tool for creating system automation processes. With syntax sugar of SSHScript, writing python scripts to execute commands on local host or remote hosts is easy. 

You just need to embed commands and networking in python scripts. SSHScript would execute them and let you handle outputs all in Python. You need not to know programming about the subprocess module and Paramiko(ssh).

Below is an example. It makes an ssh connection to the host1, then from the host1 makes a connection to the host2. Then It executes “netstat -antu” on the host2.

```
# file: hello.spy
# 1. connect to host1
with $.connect('username1@host1', password='secret') as _:

    # 2. connect to nested host2
    with $.connect('username2@host2', password='secret') as _:

        # 3. execute a command
        $netstat -antu

        # 4. handle outputs
				with open('netstat.log','w') as fd:
				    fd.write($.stdout)
```

If you did “ssh-copy-id” to remote hosts in advance, you don’t even need to give the password. 

```python
# login by a ssh key
$.connect('username1@host1')

# login by a ssh key in a path
$.connect('username1@host2',pkey=$.pkey('/path/to/keyfile'))
```

Doing nested-scp is simple too. The script below downloads the /var/log/message from the host2 and uploads config.ini on the localhost to  /tmp on the host2.

```
with $.connect('username1@host1') as _:
    with $.connect('username2@host2') as _:
        $.download('/var/log/message')
        $.upload('config.ini','/tmp')
```

Below is a longer example, it makes an ssh connection to a remote host, then prints out all its IP addresses.

```
# regular python script
import unicodedata,re
from getpass import getpass
password = getpass()

#### start of SSHScript's block
# 1. ssh to the remote host
with $.connect('username@host',password=password) as _:
    
    # 2. execute command 
    $ifconfig | grep inet
    
    # 3. collect the output
    content = $.stdout
#### end of SSHScript's block

# handle the outputs in regular python script
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

Suppose that the file is named “hello.spy”, then execute it on console by

```
sshscript hello.spy
```

the SSHScript’s CLI “sshscript” would transfer hello.spy into a regular python script, then execute the script.  In fact, “hello.spy” can contain any python statements. 

You can also use SSHScript as a regular python package by “import sshscript”. The documents page has examples for your reference.

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

![image](https://user-images.githubusercontent.com/4695577/186998717-ef372f78-daa5-4893-b9e9-2b6b8bff6114.png)



## Disclaimer

- Developing and testing on MacOS, Linux, Freebsd only. For Windows users, suggestion is to use the SSHScript in the "bash of Powershell" or the WSL.
- Please use it at your own risk.

[![Downloads](https://pepy.tech/badge/sshscript)](https://pepy.tech/project/sshscript)
