# Syntax

## $

run a single-line command

- by subprocess.popen
- by client.exec_command

<aside>
💡 “|” does not work in subprocess, but work in ssh, eg.
$ls -l | wc -l

</aside>

## $”””

Many lines of “$” put together, for example:

```jsx

$ls -l /tmp
$whoami
$hostname

```

They can be put together by 

```jsx
$"""
    ls -l /tmp
    whoami
    hostname
"""
```

Every single line are executed individually. The output of stdout or stderr are put together.

Every command is executed one by one.

## $$

Sometimes, we need a shell to work, for example:

```jsx
$$ echo “1234” | sudo -S rm -rf /goodbye-root
```

or 

```jsx
$$ echo $PATH

because, in a non-shell command, like:

$echo $PATH

the output is "$PATH"
```

or

```jsx
Also `pwd` works only in $$ not in $.
$$ echo `pwd` 
```

The command will be executed in shell. For subprocess, it means with “shell=True” for popen(). For paramiko, it means client.invoke_shell()

The output of stdout or stderr are put together in $.stdout and $.stderr respectively.

## $$”””

Many commands can put together, for example:

```jsx
$$"""
    cd /tmp
    ls -l
"""
```

They are executed in a single session of shell. 

- For subprocess, it means popen(”bash”) and commands are written to its stdin one by one.
- For paramiko, it means client.invoke_shell() and commands are written to its stdin one by one.

## with $

An interactive shell. Commands are executed in a shell and you can interactive with it.

```jsx
# Example of subprocess:
os.environ[’CMD_INTERVAL’] = "1" # 1 second between every line
os.environ['SHELL'] = '/bin/tcsh' # if you want something diffrent 
with $sudo -S su as shell:
    shell.send('root-password-is-123456')
    shell.send('cd /root')
    shell.send('pwd')
    print(shell.stdout) # /root
    shell.send('ls -l')
print($.stdout) # the outputs of all lines of execution.
```

<aside>
💡 with $”””, with $$ or with $$””” are all the same as with $

</aside>

## os.environ

### os.environ[’VERBOSE] = “1”

```jsx
if sys.stdout.isatty():
    os.environ['VERBOSE'] = "1"
```

### os.environ[’CMD_INTERVAL’] = “0.5”

The interval between two commands. Default is 0.5 seconds. Interval is count from the latest time when having data received from stdout or stderr.  This value can be changed by os.environ[’CMD_INTERVAL’]. For example:

```jsx
os.environ[’CMD_INTERVAL’] = "2"
$$"""
    hostname
    cd /tmp
    pwd
"""
# the three commands would be submitted every 2 seconds.
```

The output of stdout or stderr are put together in $.stdout and $.stderr respectively.

Reset this value by

```jsx
del os.environ[’CMD_INTERVAL’]
```

## $.stdout

You can get the output of a command from $.stdout. If many commands are executed, the $.stdout would have all of them. For example:

```python
$"""
   echo "this is a book"
   echo "that is a pen"
"""
assert $.stdout.find('this is a book') >= 0
assert $.stdout.find('that is a pen') >= 0
```

Well, for invoking shell, you would get much more.

```python
$$"""
   echo "this is a book"
   echo "that is a pen"
"""
# the $.stdout would have many control charecator.
```

## $.stderr

If your command execution dumps something from stderr, you can get them by $.stderr.

```python
$"""
cat /non-existing-file
"""
assert $.stderr.find("No such file or directory") > 0
```

There is a special note for $.stderr. Please consider the example in 3 cases:

- A. $cat /non-existed-file
- B. $$cat /non-existed-file
- C. with $$cat /non-existed-file

For local subprocess, $.stderr would have value “No such file or directory” in A, B and C.

For remote ssh session, $.stderr would have value “No such file or directory” for A only.  Since for remote ssh session, case B and C, It would be **$.stdout** have the error message “No such file or directory”, not the $.stderr. This is the behavior of the paramiko invoke_shell() which implicitly set get_pty=True.

## @{python-expression}  in command

You can embed python in command. It would be eval() before execution. For example:

```python
import datetime
now = datetime.datetime.now()
$tar -zcvf @{now.strftime("%m%d")}.tgz /var/log/system.@{now.strftime("%Y-%m-%d")} 

# if today is June 4, 1989. the command would be:
$tar -zcvf 64.tgz /var/log/system.1989-06-04
```

It also works for command in multiple lines

```python
# last folder name is "c<space>d"
import os
path = '/a/b/c d'
$"""
    ls -l "@{path}"
    ls -l "@{os.path.dirname(path)}"
"""

# is the same as
$"""
    ls -l "/a/b/c d"
    ls -l "/a/b"
"""
```

## $.client

The instance of `paramiko.client.**SSHClient**`

## $.close()

This is the counterpart of $.open(). Please see examples in $.open() section.

## $.download(src:str, dst:str)

- src: remote file to download in absolute path
- dst: local path to save the file
    - if dst is a relative path, then os.path.abspath() would be applied.
    - if the dst is a folder, the filename of src (os.path.basename(src)) would be appended.

The would download files from remote host.

```python
# suppose this script is executing on host-A
$.open('user@host-B')
myfolder = os.path.dirname(__file__)
$.download('/var/log/message',myfolder)
assert os.path.exists(os.path.join(myfolder,'message'))
```

<aside>
💡 In scenario of nested ssh, say Host-A ⇢ Host-B ⇢ Host-C. Then, download file from the Host-C. The downloaded file from the Host-C is on the Host-A, not on the Host-B.

</aside>

## $.exit()

break the execution of the sshscript script.

## $.include(filepath:str)

- filepath: the path of a sshscript file.
    - The path could be absolute or relative to the current file which doing the including.

This would include the content of another sshscript file into the position with same indent. For example:

```python
#file: a.spy
if True:
    $.open('user@host')
    $.include('b.spy')
```

```python
#file: b.spy
if True:
    $hostname
else:
    $rm -rf /
$.close()
```

The final result of a.spy is:

```python
#file: a.spy
if True:
    $.open('user@host')
    if True: # ⬅ included from b.spy
        $hostname
    else:
        $rm -rf /
    $.close()
```

The b.spy could be include as many times as you like in a.spy. Also, in b.spy, you can include another c.spy.

For preventing infinite loop of cycling including. The max times of a file to be included is 100. If you know what you are doing. You can change it by setting os.environ[’MAX_INCLUDE’]. eg.

```python
os.environ['MAX_INCLUDE'] = 999
```

## $.open(host:str,**kw)

- host: the host name to connect by ssh. This could also be in form of “username@host”.  eg. ‘tim@140.119.20.90’
- other keyword arguments would be sent to `paramiko.client.**SSHClient`.connect(). eg.**
    - username: optional, the username to login ssh server. If this is not given in “host” parameter.
    - password: optional, the password to login ssh server.
    - port: optional, the  port number to connect ssh server. default is 22.
    - pkey: optional, the RSA key to login. Please see $.pkey() section for details.
    - proxyCommand: optional.
    

Example:

```python
def save(hostname, content):
    with open(f'{hostname}.top') as fd:
        fd.write($.stdout)

user = 'user'
host1 = '1.1.1.1'
host2 = '2.2.2.2'

# If you have did "ssh-copy-id" to host1.
# Usually you don't need to give password again.
$.open(user+'@'+host1) 
$top -b -n1
save(host1, $.stdout)
$.close()

$.open(user+'@'+host2)
$top -b -n1
save(host2, $.stdout)
$.close()

```

Example of nested ssh.

```python
def save(hostname, content):
    with open(f'{hostname}.top') as fd:
        fd.write($.stdout)

user = 'user'
host1 = '1.1.1.1'
host2 = '2.2.2.2'

$.open(user+'@'+host1) 
$top -b -n1
save(host1, $.stdout)
#⬇ If you do not $.close() this connection.
#⬇ The next $.open would be a nested ssh.
#⬇ You would ssh to host2 from host1, not from the localhost.
#$.close() 

pkey = $.pkey('/home/user/.ssh/id_rsa')
$.open(user+'@'+host2,pkey=pkey)
$top -b -n1
save(host2, $.stdout)
$.close()
```

The example below would be more clear for showing nested ssh scenario.

```python
def save(hostname, content):
    with open(f'{hostname}.top') as fd:
        fd.write($.stdout)

user = 'user'
host1 = '1.1.1.1'
host2 = '2.2.2.2'

with $.open(user+'@'+host1) as _:
    $top -b -n1
    save(host1, $.stdout)
    
    #⬇ ssh to host2 via host1
    pkey = $.pkey('/home/user/.ssh/id_rsa') #⬅ key path in host1
    $.open(user+'@'+host2,pkey=pkey)
    $top -b -n1
    save(host2, $.stdout)

```

For security reason, you can use key file in [localhost](http://localhost), thus the key file in host1 could be removed. for example:

```python
def save(hostname, content):
    with open(f'{hostname}.top') as fd:
        fd.write($.stdout)

user = 'user'
host1 = '1.1.1.1'
host2 = '2.2.2.2'
pkey = $.pkey('/home/user/.ssh/id_rsa') #⬅ key path in localhost

with $.open(user+'@'+host1) as _:
    $top -b -n1
    save(host1, $.stdout)
    
    #⬇ ssh to host2 from host1 by key in localhost
    $.open(user+'@'+host2,pkey=pkey)
    $top -b -n1
    save(host2, $.stdout)
```

Please be noted that the proxyCommand does not work in nested ssh, for example:

```python
host = 'user@1.1.1.1'
proxyCommand='openssl s_client -connect 8.8.8.8:443'
with $.open(host,proxyCommand=proxyCommand) as _:
    $hostname

    host2 = 'user@2.2.2.2"
    # proxyCommand in nested ssh does not work
    with $open(host2,proxyCommand=proxyCommand) as _:
        $hostname
    
    # this works
    keypath = '/home/user/.ssh/id_rsa'
    with $open(host2,pkey=$.pkey(keypath)) as _:
        $hostname
    
```

## $.panaroid(boolean:)

## $.pkey(filepath:str)

- filepath: path of the RSA key.

Login with RSA key

```python
pkey = $.pkey('/home/user/.ssh/id_rsa')
open('user@host',pkey=pkey)
```

## $.sftp

The instance of `paramiko.sftp_client.**SFTP**`

## $.timeout(int:)

## $.upload(src-local,dst-remote,makedirs=0,overwrite=1)

## __export__ = [’name’,...]

## __export__ = [’*’]

## CLI

### [sshscript](http://sshscript.py) [file or folder]

### [sshscript](http://sshscript.py) [file or folder]  -- script
