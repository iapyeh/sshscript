#### SSHScript 2.0 Tutorial

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
import sshscript
session = sshscript.SSHScriptSession()
session('hostname')
print(f'hostname is {session.stdout.strip()}')
session('whoami')
print(f'I am {session.stdout.strip()}')
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

### Symbols

- ⏚ : local

- 🌎 : remote

- ＄ : SSHScript dollar-syntax

- 🐍  : SSHScript module