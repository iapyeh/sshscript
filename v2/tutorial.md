# SSHScript 2.0 Tutorial

<div style="text-align:right"><a href="./index">Index</a></div>

# Automating Shell Tasks in Python

* [Execute commands: one-dollar ($)](#one-dolar)
* [Execute shell commands: two-dollars($$)](#two-dolars)
* [Invoke an interactive console: with-dollar(with $)](#with-dollar)
* [Invoke an interactive root console: $.sudo()](#dollar-sudo)
* [Invoke another user interactive console: $.su()](#dollar-su)
* [Execute interactive commands : $.enter()](#dollar-enter)
* [Execute foreground programs : $.iterate()](#dollar-iterate)

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

## 🔵 <a name="dollar-sudo"></a>Invoke an interactive root console: $.sudo()

### ⏚＄ Invoke an interactive root console on localhost using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
with $.sudo('1234') as console:
    console('cd /root')
    assert console.exitcode == 0
    console('whoami')
    assert 'root' in console.stdout
```

### ⏚🐍 Invoke an interactive root console on localhost using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.sudo('1234') as console:
    console('cd /root')
    assert console.exitcode == 0
    console('whoami')
    assert 'root' in console.stdout
```

### 🌎＄ Invoke an interactive root console on remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234') as host:
    with host.sudo('1234') as sudo:
        sudo('cd /root')
        assert sudo.exitcode == 0 ## success
        sudo('whoami')
        assert 'root' in sudo.stdout
```

### 🌎🐍 Invoke an interactive root console on remote host using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    with remote_session.sudo('1234') as console:
        console('cd /root')
        assert console.exitcode == 0
        console('whoami')
        assert 'root' in console.stdout
```

## 🔵 <a name="dollar-su"></a>Invoke another user interactive console: $.su()

### ⏚＄ Invoke another user interactive console on localhost using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
## suppose that your have to su to "sudoer" before getting the root console
with $.su('sudoer','1234') console:
    console('whoami')
    assert 'sudoer' in console.stdout
    with console.sudo('1234') as sudo_console:
        sudo_console('whoami')
        assert 'root' in sudo_console.stdout
```

### ⏚🐍 Invoke another user interactive console on localhost using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.su('sudoer','1234') as console:
    with console.sudo('1234') as sudo_console:
        sudo_console('whoami')
        assert 'root' in sudo_console.stdout
```

### 🌎＄ Invoke another user interactive console on remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234') as host:
    with host.su('sudoer','1234') as console:
        console('whoami')
        assert 'sudoer' in console.stdout
        with console.sudo('1234') as sudo_console:
            sudo_console('whoami')
            assert 'root' in sudo_console.stdout
```

### 🌎🐍 Invoke another user interactive console on remote host using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    with remote_session.su('sudoer','1234') as console:
        with console.sudo('1234') as sudoconsole:
            sudoconsole('whoami')
            assert 'root' in sudoconsole.stdout
```
## 🔵 <a name="dollar-enter"></a>Execute interactive commands: $.enter()

### ⏚＄ Execute interactive commands on localhost using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
## This example executes "mysql", waiting for "password" to be prompted,
## and then input "1234". When all statements are executed, send "quit\n" to stop this process.
with $.enter('mysql -uroot -p dbname','password','1234',exit='quit') as mysql:
    mysql("ALTER USER 'root'@'localhost' IDENTIFIED BY 'MyN3wP4ssw0rd';")
    mysql('show slave status\G;');
    for line in mysql.stdout.splitlines():
        if ':' in line:
            key,value = [x.strip() for x in line.split(':')]
```

### ⏚🐍 Execute interactive commands on localhost using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
## The example would upload new version to the Pipy.
## Since this command would be terminated automatically, so we set exit=False,
## Which means that there is nothing to input when exiting the "with closure".
with session.enter(f'python3 -m twine upload version.2.tgz',exit=False) as pipyupdate:
    pipyupdate.expect('username')
    pipyupdate('tony')
    pipyupdate.expect('password')
    pipyupdate('password-of-tony')
```

### 🌎＄ Execute interactive commands on remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234') as host:
    with host.enter('mysql -uroot -p dbname','password','1234',exit='quit') as mysql:
        mysql("ALTER USER 'root'@'localhost' IDENTIFIED BY 'MyN3wP4ssw0rd';")
        mysql('show slave status\G;');
        for line in mysql.stdout.splitlines():
            if ':' in line:
                key,value = [x.strip() for x in line.split(':')]
```

### 🌎🐍 Execute interactive commands on remote host using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    with remote_session.enter('python3') as python3:
        python3('import helloworld')
        if 'ModuleNotFoundError' in python3.stdout:
            print('helloworld module is not installed on host')
```

## 🔵 <a name="dollar-iterate"></a>Execute foreground programs: $.iterate()

"Foreground programs" is a name to describe programs like "tcpdump" that run in the foreground and require user interaction to stop. These programs run in the active terminal session and hold it until the user takes action to terminate them. 


### ⏚＄ Execute foreground programs on localhost using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
## This example executes "mysql", waiting for "password" to be prompted,
## and then input "1234". When all statements are executed, send "quit\n" to stop this process.
with $.sudo('1234') as sudo:
    with sudo.iterate('tcpdump -vv') as loopable:
        for line in loopable:
            print(line)
            ## should break by some reason
            if line.find('192.168.131.79'): break
```

### ⏚🐍 Execute foreground programs on localhost using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.sudo('1234') as sudo:
    with sudo.iterate('tcpdump -vv') as loopable:
        for line in loopable:
            print(line)
            ## should break by some reason
            if line.find('192.168.131.79'): break
```

### 🌎＄ Execute foreground programs on remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234') as host:
    with host.sudo('1234') as sudo:
        with sudo.iterate('tcpdump -vv') as loopable:
            for line in loopable:
                print(line)
                ## should break by some reason
                if line.find('192.168.131.79'): break
```

### 🌎🐍 Execute foreground programs on remote host using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as remote_session:
    with remote_session.sudo('1234') as sudo:
        with sudo.iterate('tcpdump -vv') as loopable:
            for line in loopable:
                print(line)
                ## should break by some reason
                if line.find('192.168.131.79'): break
```

### Symbols

- ⏚ : local

- 🌎 : remote

- ＄ : SSHScript dollar-syntax

- 🐍  : SSHScript module