# SSHScript v2.0 Core Features

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Execute interactive commands : $.enter()](#dollar-enter)
* [Execute foreground programs : $.iterate()](#dollar-iterate)

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