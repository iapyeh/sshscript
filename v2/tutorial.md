# SSHScript v2.0 Commands Execution and Console

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Execute commands: one-dollar ($)](#one-dolar)
* [Execute shell commands: two-dollars($$)](#two-dolars)
* [Invoke an interactive console: with-dollar(with $)](#with-dollar)

## 🔵 <a name="one-dollar"></a>Execute commands: one-dollar ($)

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

Example of connecting to a nested remote host:
```
with $.connect('user@host','1234'):
    with $.connect('user@host2','5678'):
        $hostname
        print(f'hostname is {$.stdout.strip()}')
        $whoami
        print(f'I am {$.stdout.strip()}')
```


### 🌎🐍 Execute commands on remote host using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    remote_session('hostname')
    print(f'hostname is {remote_session.stdout.strip()}')
    remote_session('whoami')
    print(f'I am {remote_session.stdout.strip()}')
```

Example of connecting to a nested remote host:

```
## filename: example.py
## run: python3 example.py
with session.connect('user@host','1234') as remote_session:
    ## instead of using password, you can provide a paramiko pkey.
    ## (should give a absolute path to the key file)
    pkey = remote_session.pkey('/home/user/.ssh/id_rsa')
    with remote_session.connect('user@host2',pkey=pkey) as nested_remote:
        nested_remote('hostname')
        print(f'hostname is {nested_remote.stdout.strip()}')
        nested_remote('whoami')
        print(f'I am {nested_remote.stdout.strip()}')
```

## 🔵 <a name="two-dollars"></a> Execute shell commands: two-dollars($$)

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
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    remote_session('ls -l | grep ^d',shell=True)
    for line in remote_session.stdout.splitlines():
        print('Folder:' + line)
```


## 🔵 <a name="with-dollar"></a>Invoke an interactive console: with-dollar(with $)

### ⏚＄ Invoke an interactive console on localhost using the SSHScript dollar-syntax
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


### ⏚🐍 Invoke an interactive console on localhost using the SSHScript module

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


### 🌎＄ Invoke an interactive console on remote host using the SSHScript dollar-syntax
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

### 🌎🐍 Invoke an interactive console on remote host using the SSHScript module

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