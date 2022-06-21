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

Because the “sudo” requires a “pty” to work. The other reason is that environment works only in shell mode. For example:

```jsx
$$ echo $PATH

#You will get the value of $PATH. But In a non-shell command, like:

$echo $PATH

#the output is $PATH, not the value of $PATH
```

The inline command also requires a shell to work.

```jsx
# `pwd` works only in $$ not in $.
$$ echo `pwd` 
```

Commands will be executed in shell. For subprocess, it means with “shell=True” for popen(). For paramiko, it means client.invoke_shell()

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

For multiple commands, the output of stdout or stderr are put together in $.stdout and $.stderr respectively.

## with $

This syntax would invoking an interactive shell. Commands are executed in a shell and you can interactive with it.

```jsx
# Example of subprocess:
os.environ[’CMD_INTERVAL’] = "1" # 1 second between every line
os.environ['SHELL'] = '/bin/tcsh' # if you want something diffrent 
with $sudo -S su as console:
    console.send('root-password-is-123456')
    console.send('cd /tmp')
    console.send('pwd')
    print(console.stdout) # /tmp
    console.send('cd /root')
    console.send('pwd')
    print(console.stdout) # /root
    console.send('ls -l')
print($.stdout) # the outputs of all lines of execution.
```

About the “console” in above example. It is an instance of POpenChannel,POpenPipeChannel or ParamikoChannel. Which one does not matter, the following methods and properties are available for your interaction:

- sendline(command, waitingSeconds=1)
    - command: str
        - a line of command to input to the console (no tailing newline required)
    - waitingSeconds: int, default is 1
        - at least, how many seconds to wait for data after submitting the seconds.
- stdout
    - you can get the stdout output of just executed command from this property.
- stderr
    - you can get the stderr output of just executed command from this property.
- expect(keyword, timeout=60)
    - keyword: str, case insensitive.
        - blocks the execution until given keyword appears in stdout or stderr.
        - keyword can also be a string re.Pattern.
    - timeout: seconds to wait. If it reaches overtime, raises a TimeoutError.
- expectStderr(keyword, timeout=60)
    - blocks the execution until given keyword appears in stderr.
    - timeout: seconds to wait. If it reaches overtime, raises a TimeoutError.
- expectStdout(keyword, timeout=60)
    - blocks the execution until given keyword appears in stdout.
    - timeout: seconds to wait. If it reaches overtime, raises a TimeoutError.

Example of using the “waitingSeconds” parameter:

```python
with $PS1=;export PS1 as console:
    # at least wait 2 seconds before inputing password
    console.sendline('sudo -S lastb -F -10',2) 
    console.sendline('1234')
print($.stdout)
```

Another implementation style with “expect”.

```python
import re
with $PS1=;export PS1 as console:
    console.sendline('sudo -S lastb -F -10',2) 

    # wait for "password" to appear before inputing password
    console.expect('password')
    # another way is to set a string re.Pattern for expect()
    #console.expect(re.compile('PASSWORD',re.I))

    console.sendline('your-password')
print($.stdout)
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

### os.environ[’CMD_TIMEOUT’] = “60”

The max time spent for execution a command in seconds. Default is 60 seconds.

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

If you know what you are doing, you can get the instance of paramiko.client.SSHClient for your own purpose. Before accessing this value, “$.connect()” should be called to open a ssh session.

## $.close()

This is the counterpart of $.connect(). Please see examples in $.connect() section. Actually, you don’t need to call this in context of “with $.connect()”. But you do need this sometimes.

## $.connect(host,**kw)

- host: the host name to connect by ssh. This could also be in form of “username@host”.  eg. ‘tim@140.119.20.90’

Other keyword arguments were sent to [paramiko.client.SSHClient.connect()](https://docs.paramiko.org/en/stable/api/client.html)**.**  Some of them are:

- username: the username to login ssh server. If this is not given in “host” parameter.
- password:  the password to login ssh server.
- port: the  port number to connect ssh server. default is 22.
- pkey: the RSA key to login. Please see $.pkey() section for details.
- proxyCommand.
- timeout

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
$.connect(user+'@'+host1) 
$top -b -n1
save(host1, $.stdout)
$.close()

$.connect(user+'@'+host2)
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

$.connect(user+'@'+host1) 
$top -b -n1
save(host1, $.stdout)
#⬇ If you do not $.close() this connection.
#⬇ The next $.connect would be a nested ssh.
#⬇ You would ssh to host2 from host1, not from the localhost.
#$.close() 

pkey = $.pkey('/home/user/.ssh/id_rsa')
$.connect(user+'@'+host2,pkey=pkey)
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

with $.connect(user+'@'+host1) as _:
    $top -b -n1
    save(host1, $.stdout)
    
    #⬇ ssh to host2 via host1
    pkey = $.pkey('/home/user/.ssh/id_rsa') #⬅ key path in host1
    $.connect(user+'@'+host2,pkey=pkey)
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

with $.connect(user+'@'+host1) as _:
    $top -b -n1
    save(host1, $.stdout)
    
    #⬇ ssh to host2 from host1 by key in localhost
    $.connect(user+'@'+host2,pkey=pkey)
    $top -b -n1
    save(host2, $.stdout)
```

Please be noted that the proxyCommand does not work in nested ssh, for example:

```python
host = 'user@1.1.1.1'
proxyCommand='openssl s_client -connect 8.8.8.8:443'
with $.connect(host,proxyCommand=proxyCommand) as _:
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

## $.download(src, dst=None)

- src: str, remote file to download in absolute path
- dst: str; optional, local path to save the file
    - If the dst is a relative path, then os.path.abspath() would be applied to it.
    - The dst could be a folder. The downloaded filename would be the same as the src.
    - If dst is None, default is saving to the folder of os.getcwd().
- Return: tuple (src, dst)

The would download files from remote host.

```python
# suppose this script is executing on host-A
$.connect('user@host-B')
myfolder = os.path.dirname(__file__)
src, dst = $.download('/var/log/message',myfolder)
assert os.path.exists(os.path.join(myfolder,'message'))
```

<aside>
💡 In scenario of nested ssh, say Host-A ⇢ Host-B ⇢ Host-C. Then, download file from the Host-C. The downloaded file from the Host-C is on the Host-A, not on the Host-B.

</aside>

<aside>
💡 If the behavior of $.download is not what you expected, you can access the $.sftp for better control.

</aside>

## $.exit()

break the execution of the sshscript script.

```python
$uname -a

# MacOS has "Darwin" in the output of "uname"
# Let's stop the execution for all others.
if $.stdout.find('Darwin') == -1:
    $.exit()

# this command is only executing on MacOS
$rm -rf /Users/jobs
```

Example:

```python
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('-p','--password', dest='password', default='',
                    help='root password to login to care database')
args, unknown = parser.parse_known_args(__main__.parameters)
if not args.password :
    parser.print_help()
    $.exit()

$mysqladmin -uroot -p "@{args.password}" create girlfriends
```

## $.include(filepath)

- filepath: str, the path of a sshscript file.
    - The path could be absolute or relative to the current file which doing the including.

This would include the content of another sshscript file into the position with same indent. For example:

```python
#file: a.spy
if True:
    $.connect('user@host')
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
    $.connect('user@host')
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

## $.panaroid(yes)

- yes: boolean. If True, stop the execution if there is any data received from stderr. Default is false.

## $.pkey(filepath)

- filepath: path of the RSA key.
- Return: an instance of paramiko.pkey.PKey

get the RSA key for a file path. This works both in local and remote.

```python
# implement "multi-hop scp"
# but be more flexible, simple and easy to extend
import datetime
pkey = $.pkey('/home/user/.ssh/id_rsa')
today = datetime.datetime.now()
with open('user@host',pkey=pkey) as _:
    pkeyOnRemoteHost = $.pkey('/home/user2/.ssh/id_rsa')
    with open('user2@host2',pkey=pkeyOnRemoteHost) as _:
        $hostname
        assert $.stdout.startswith('host2')
        $.download(f'/var/log/nginx/log-{today.strftime("%m-%d")}')
```

## $.sftp

If you know what you are doing, you can get the instance of paramiko.sftp_client.SFTP for your own purpose. Before accessing this value, “$.connect()” should be called to open a ssh session.

## $.upload(src, dst, makedirs=0, overwrite=1)

- src: str, the file path in [localhost](http://localhost) to upload.
    - if this value is a relative path, os.path.abspath() is applied.
- dst: str, the file path in remote to save the uploaded file, must be absolute path
- makedirs: boolean; optional, default is False.
    - create intermediate folders of the dst path. default is False. If the destination folder is not existed, a FileNotFound exception would be raised.
- overwrite: boolean; optional, default is True.
    - if True, overwrites the destination file if it is already there, otherwise raises a FileExistsError.
- Return: tuple (src, dst)

```python
$.connect('root@host')

$upload('/home/user/mysql.cnf','/etc/mysql.cnf')

# or, giving a destination folder. 
# default is to overwrite existing file
$upload('/home/user/mysql.cnf','/etc')

# this would upload to /etc/mysql/master/backup/mysql.cnf
# and create folder /etc/mysql, /etc/mysql/master and
# /etc/mysql/master/backup if any of them is not existed yet.
$upload('/home/user/mysql.cnf','/etc/mysql/master/backup/',makedirs=1)

```

<aside>
💡 If the behavior of $.upload is not what you expected, you can access the $.sftp for better control.

</aside>

## __export__ = [’name’,...]

## __export__ = [’*’]

##