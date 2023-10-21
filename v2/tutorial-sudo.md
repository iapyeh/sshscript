# SSHScript v2.0 Core Features

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Invoke an interactive root console: $.sudo()](#dollar-sudo)
* [Invoke another user interactive console: $.su()](#dollar-su)
* [Execute interactive commands : $.enter()](#dollar-enter)
* [Execute foreground programs : $.iterate()](#dollar-iterate)

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