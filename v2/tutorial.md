# SSHScript 2.0 Tutorial

<div style="text-align:right"><a href="./index">Index</a></div>

# Automating Shell Tasks in Python

## Execute commands

### ⏚＄ Execute commands on localhost using the SSHScript dollar-syntax
```
## filename: example.spy
## run 1: sshscript example.spy
## run 2: sshscript --verbose --debug example.spy
## run 3: sshscript --verbose --debug 8 example.spy
$hostname
print(f'hostname is {$.stdout.strip()}')
$whoami
print(f'I am {$.stdout.strip()}')
```

### ⏚🐍 Execute commands on localhost using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
session('hostname')
print(f'hostname is {session.stdout.strip()}')
session('whoami')
print(f'I am {session.stdout.strip()}')
```

For execution details, insert the following content at the beginning of the example:
```
import os
os.environ['VERBOSE'] = 'yes'
os.environ['DEBUG'] = 'yes'
## more details
#os.environ['DEBUG'] = '8'

sshscript.setupLogger()
```


### 🌎＄ Execute commands on remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
## '1234' is the password. If no password is provided,
## "~/.ssh/id_rsa" would be used (Paramiko's feature).
with $.connect('user@host','1234'):
    $hostname
    print(f'hostname is {$.stdout.strip()}')
    $whoami
    print(f'I am {$.stdout.strip()}')
```

### 🌎🐍 Execute commands on remote host using the SSHScript module

```
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    remote_session('hostname')
    print(f'hostname is {remote_session.stdout.strip()}')
    remote_session('whoami')
    print(f'I am {remote_session.stdout.strip()}')
```

## Execute shell commands

Shell commands are commands that must be executed by a shell. They can be used to perform a variety of tasks, such as:

- Running multiple commands in sequence (pipe lines)
- Accessing and modifying environment variables (e.g., ls $HOME)

Note that the output of shell commands may include additional context that depends on environment variables and shells.


### ⏚＄ Execute shell commands on localhost using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
$$ls -l | grep ^d
for line in $.stdout.splitlines():
    print('Folder:' + line)
```

### ⏚🐍 Execute shell commands on localhost using the SSHScript module

```
import sshscript
session = sshscript.SSHScriptSession()
session('ls -l | grep ^d',shell=True)
for line in session.stdout.splitlines():
    print('Folder:' + line)
```

### 🌎＄ Execute shell commands on remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234'):
    $$ls -l | grep ^d
    for line in $.stdout.splitlines():
        print('Folder:' + line)
```

### 🌎🐍 Execute shell commands on remote host using the SSHScript module

```
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    remote_session('ls -l | grep ^d',shell=True)
    for line in remote_session.stdout.splitlines():
        print('Folder:' + line)
```


## Invoke an interactive console to run commands

### ⏚＄ Invoke an interactive console to run commands on localhost using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
with $:
    $cd $HOME
    $[ -e .ssh/id_rsa ]
    if $.exitcode == 1:
        ## ~/.ssh/id_rsa does not exist.
        ## Lets run ssh-keygen without prompt to create it.
        $ssh-keygen -t rsa -N ''
```

You can also assign the shell by "$#!/bin/bash", eg:
```
with $#!/bin/bash:
    $cd $HOME
```


### ⏚🐍 Invoke an interactive console to run commands on localhost using the SSHScript module

```
import sshscript
session = sshscript.SSHScriptSession()
with session.shell() as console:
    console('cd $HOME')
    console('[ -e .ssh/id_rsa ]')
    if console.exitcode == 1:
        console("ssh-keygen -t rsa -N ''")
```

You can also assign the shell by "$#!/bin/bash", eg:
```
with session.shell('#!/bin/bash') as console:
    console('cd $HOME')
```


### 🌎＄ Invoke an interactive console to run commands on remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234'):
    with $:
        $cd $HOME
        $[ -e .ssh/id_rsa ]
        if $.exitcode == 1:
            ## ~/.ssh/id_rsa does not exist.
            ## Lets run ssh-keygen without prompt to create it.
            $ssh-keygen -t rsa -N ''
```

### 🌎🐍 Invoke an interactive console to run commands on remote host using the SSHScript module

```
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    with remote_session.shell() as console:
        console('cd $HOME')
        console('[ -e .ssh/id_rsa ]')
        if console.exitcode == 1:
            console("ssh-keygen -t rsa -N ''")
```



### Symbols

- ⏚ : local

- 🌎 : remote

- ＄ : SSHScript dollar-syntax

- 🐍  : SSHScript module