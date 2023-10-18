# SSHScript Documents



#### v1.1.17 supports streaming-style commands (tcpdump). Released on 2022/9/22, [Release Notes](https://iapyeh.github.io/sshscript/release-v1.1.17)

## en

- [Tutorial](https://iapyeh.github.io/sshscript/v1/tutorial) 
- [Learning SSHScript Chapter 1](https://iapyeh.github.io/sshscript/v1/learn-chap01)
- [Learning SSHScript Chapter 2](https://iapyeh.github.io/sshscript/v1/learn-chap02)
- [Syntax, Variables and Functions](https://iapyeh.github.io/sshscript/v1/syntax)
- [sshscript CLI](https://iapyeh.github.io/sshscript/v1/cli)
- [sshscript Module](https://iapyeh.github.io/sshscript/v1/module) 
- [Ways to get a root’s console](https://iapyeh.github.io/sshscriptv1/examples/root-console)
- [Do logging](https://iapyeh.github.io/sshscript/v1/examples/logger)
- [Troubleshooting of installation](https://iapyeh.github.io/sshscript/v1/sshscript-problem)

## zh-TW

- [導覽(Tutorial)](https://iapyeh.github.io/sshscript/v1/tutorial.zh-tw)
- [使用SSHScript教學一(Learning SSHScript Chapter 1)](https://iapyeh.github.io/sshscript/v1/learn-chap01.zh-tw)
- [使用SSHScript教學二(Learning SSHScript Chapter 2)](https://iapyeh.github.io/sshscript/v1/learn-chap02.zh-tw)
- [用 Python 作系統自動化](https://iapyeh.github.io/sshscript/v1/automationinpython-tw)
- [安裝有問題](https://iapyeh.github.io/sshscript/v1/sshscript-problem.zh-tw)

## Introduction

System automation is the process of using computer software to automatically perform routine or repetitive tasks. SSHScript is a tool that makes it easy to use Python for system automation by providing a simple syntax for executing commands on local or remote hosts. With SSHScript, you can embed commands and networking in your Python scripts, and SSHScript will handle the execution and output, so you don't need to have expertise in the subprocess module or Paramiko (ssh) to use it.

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

## Install

```
pip install sshscript
```
## Upgrade

```
pip install sshscript --upgrade
```
or
```
pip install sshscript==1.1.17
```


## Examples

- [Examples](https://iapyeh.github.io/sshscript/examples) 

## Why and Features

The idea behind SSHScript is to provide a simple and intuitive way to automate common tasks that involve running commands and dealing with outputs on local and remote hosts. SSHScript makes it easy to write scripts that can connect to remote hosts via ssh and execute commands, and it allows you to process the resulting data directly in Python. This enables you to build complex data structures and processing flows using an object-oriented approach.

Some key benefits of using SSHScript include:

- Easy to use. If you know what commands to run and which host to connect to via ssh, you can write your script without having to learn any extra concepts.

- Embedding shell commands in Python scripts is intuitive and self-explanatory, making it easy to collaborate and maintain your scripts.

- Handling execution outputs and exceptions is easier in Python than it is in shell scripts.

- Your scripts can leverage the vast ecosystem of Python packages.

- SSHScript supports parallel execution of commands using threads.

![image](https://user-images.githubusercontent.com/4695577/186998717-ef372f78-daa5-4893-b9e9-2b6b8bff6114.png)


## Releases

#### 2022/09/22 v1.1.17 supports streaming-style commands. [Release Notes](https://iapyeh.github.io/sshscript/v1/release-v1.1.17)

#### 2022/09/05 v1.1.16 supports powershell(Windows). [Release Notes](https://iapyeh.github.io/sshscript/v1/release-v1.1.16)

#### 2022/08/24 v1.1.14 supports thread. [Release Notes](https://iapyeh.github.io/sshscript/release-v1.1.14)

[![Downloads](https://pepy.tech/badge/sshscript)](https://pepy.tech/project/sshscript)
