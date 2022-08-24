<div style="text-align:right"><a href="./index">Index</a></div>

# Syntax, Variables and Functions

#### Please be noted: This article is obsoleted, new version for v1.1.14 is coming soon. (2022/8/24)

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

Every single line is executed individually. The output of stdout or stderr are put together.

Every command is executed one by one.

## $$

Sometimes, we need a shell to work, for example:

```jsx
$$ echo “1234” | sudo -S rm -rf /goodbye-root
```

Because the “sudo” requires a “pty” to work. The other reason is that the environment works only in shell mode. For example:

```jsx
# You will get the value of $PATH. 
$$ echo $PATH

# But in a non-shell command,
# the output is $PATH, not the value of $PATH
$echo $PATH

```

The inline command also requires a shell to work.

```jsx
# `pwd` works only in $$ not in $.
$$ echo `pwd` 
```

$$-commands will be executed in a shell. For the subprocess, it is implemented by popen(shell=True). For the Paramiko, it is implemented by client.invoke_shell()

## $$”””

Many commands can be put together, for example:

```jsx
$$"""
    cd /tmp
    ls -l
"""
```

They are executed in a single session of shell. 

- For the subprocess, it means popen(”bash”), and commands are written to its stdin one by one.
- For the Paramiko, it means client.invoke_shell(), and commands are written to its stdin one by one.

For multiple commands, their output of stdout or stderr are put together in $.stdout and $.stderr respectively.

## with $

This syntax would invoke an interactive shell. Commands are executed in a shell and you can interact with it.

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

About the “console” in the above example. It is an instance of POpenChannel,POpenPipeChannel or ParamikoChannel. Which one does not matter, the following methods and properties are available for your interaction:

- sendline(command, waitingSeconds=1)
    - command: str
        - command to input to the console (no tailing newline required)
    - waitingSeconds: int, default is 1
        - seconds to wait for data after submitting the seconds.
- stdout
    - you can get the stdout output of last executed command from this property.
- stderr
    - you can get the stderr output of last executed command from this property.
- expect(keyword, timeout=60)
    - keyword: str, case insensitive.
        - blocks the execution until the given keyword appears in stdout or stderr.
        - keyword can also be a string re.Pattern.
    - timeout: seconds to wait. If time is over, raises a TimeoutError.
- expectStderr(keyword, timeout=60)
    - blocks the execution until the given keyword appears in stderr.
    - timeout: seconds to wait. If time is over, raises a TimeoutError.
- expectStdout(keyword, timeout=60)
    - blocks the execution until the given keyword appears in stdout.
    - timeout: seconds to wait. If time is over, raises a TimeoutError.

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

## @{python-code}  in command

You can embed python variables in $-command. It would be evaluated before executing the command. For example:

```python
import datetime
now = datetime.datetime.now()
$tar -zcvf @{now.strftime("%m%d")}.tgz /var/log/system.@{now.strftime("%Y-%m-%d")} 

# if today is June 4, 1989. the command would be:
$tar -zcvf 64.tgz /var/log/system.1989-06-04
```

It also works in commands of multiple lines:

```python
# last folder name is "c<space>d"
import os
path = '/a/b/c d'
$"""
    ls -l "@{path}"
    ls -l "@{os.path.dirname(path)}"
"""

# is evaluated to be:
$"""
    ls -l "/a/b/c d"
    ls -l "/a/b"
"""
```

# Variables

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

Please be noted, when shell is invoked, terminal control characters might be mixed in the content of stdout and stderr.

```python
$$"""
   echo "this is a book"
   echo "that is a pen"
"""
# the $.stdout would have many control characters.
```

## $.stderr

If your command execution dumps something in stderr, you can get them by $.stderr.

```python
$"""
cat /non-existing-file
"""
assert $.stderr.find("No such file or directory") > 0
```

There is a special note for $.stderr. Please consider the three examples below:

- A: $cat /non-existed-file
- B: $$cat /non-existed-file
- C: with $$cat /non-existed-file

On the localhost (subprocess), $.stderr would have value “No such file or directory” in A, B and C.

On a remote server (ssh connection), $.stderr would have value “No such file or directory” for A only. Since for remote ssh sessions, case B and C, It would be $.stdout that has the error message “No such file or directory”, not the $.stderr. This is the behavior of the Paramiko invoke_shell() which implicitly sets get_pty=True.

## $.client

The instance of paramiko.client.SSHClient of current ssh session. If you know what you are doing, you can get the instance of paramiko.client.SSHClient for your own purpose. Before accessing this value, “$.connect()” should be called to open a ssh session.

## $.sftp

If you know what you are doing, you can get the instance of paramiko.sftp_client.SFTP for your own purpose. Before accessing this value, “$.connect()” should be called to open a ssh session.

## os.environ

### os.environ[’CMD_INTERVAL’]

Default is 0.5 (seconds).

The interval between two commands. Interval is counted from the latest time when having data received from stdout or stderr.  This value can be changed by os.environ[’CMD_INTERVAL’]. For example:

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

You can reset this value by

```jsx
del os.environ[’CMD_INTERVAL’]
```

### os.environ[’CMD_TIMEOUT’]

The max time spent for executing a command in seconds.

Default is 60 seconds.

### os.environ[’SHELL’]

This is used when the subprocess is invoking shell. Usually it is set by your shell. You don’t need to bother it. If it is not set, shutil.which('bash') is called to find the shell to invoke.

### os.environ[’VERBOSE]

Default is “” (empty string)

The verbose mode is enabled by setting this value to non-empty string. When the verbose mode is enabled, every message received from stdout and stderr of the executing command would be shown on console.

You can enable it like this example:

```jsx
if sys.stdout.isatty():
    os.environ['VERBOSE'] = "1"
```

### os.environ[’VERBOSE_STDOUT_PREFIX’]

Default is 🟩

In verbose mode, This string is prefixed to every line when showing a messages of stdout on console.

### os.environ[’VERBOSE_STDERR_PREFIX’]

 Default is 🟨.

In verbose mode, This string is prefixed to every line when showing a messages of stderr on console.

## \_\_main\_\_

### \_\_main\_\_.SSHScript.logger

You can assess the logger of the SSHScript by this variable. Below is an example of setting log files in a .spy file.

```
import __main__
logger = __main__.SSHScript.logger

logfile = 'unittest.log'
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(logfile, 'w', 'utf-8')
logger.addHandler(handler)
```

### \_\_main\_\_.unknown_args

The sshscript use argparse to parsing command-line arguments. It puts those unknown argements in \_\_main\_\_.unknown_args. You can use “argparse” in .spy file by parsing this variable. For example:

```
# file content of test.spy
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--account', dest='account', action='store',default='')
args, unknown = parser.parse_known_args(__main__.unknown_args)

# in some circumstance, next line also works
#args, unknown = parser.parse_known_args()

if not args.account:
    parser.print_help()
    $.exit()
$.connect(args.account)
$netstat -antu
print($.stdout)
```

Then run it by 

```
$sshscript test.spy --account=username@host
```

# Functions

## $.close()

To close the current ssh connection. This is the counterpart of $.connect(). Please see examples in the $.connect() section. Actually, you don’t need to call this in the context of “with $.connect()”. But you do need this in some context.

## $.connect(host, username, password, port, policy,**kw)

This function open a ssh connection to remote host.

- host(str): the host name to connect. It also accepts  “username@host” format.  eg. ‘tim@140.119.20.90’
- username(str): optional, the username to login ssh server. If this is not given in the “host” parameter.
- password(str): optional, the password to login ssh server.
- port(int): optional, the  port number to connect ssh server. default is 22.
- policy: optional, the policy for SSHClient.set_missing_host_key_policy.  The default is "paramiko.client.AutoAddPolicy”.  If this value is False, there is no policy been applied. For other values, please see [more details](https://docs.paramiko.org/en/stable/api/client.html).
- **kw: other keyword arguments would be sent to [paramiko.client.SSHClient.connect()](https://docs.paramiko.org/en/stable/api/client.html)**.**  For example, some of them are:
    - pkey(paramiko.pkey.PKey): the RSA key to login. Please see the $.pkey() section for details.
    - proxyCommand.
    - timeout

Example: connect to two hosts one-by-one.

```python
def save(hostname, content):
    with open(f'{hostname}.top') as fd:
        fd.write($.stdout)

user = 'john'
host1 = '1.1.1.1'
host2 = '2.2.2.2'

# If you have did "ssh-copy-id" to the host1.
# Usually you don't need to give the password again.
$.connect(user+'@'+host1) 
$top -b -n1
save(host1, $.stdout)
$.close()

$.connect(user+'@'+host2)
$top -b -n1
save(host2, $.stdout)
$.close()

```

Example: connect to a host behind another host.

```python
def save(hostname, content):
    with open(f'{hostname}.top') as fd:
        fd.write($.stdout)

user = 'pauline'
host1 = '1.1.1.1'
host2 = '2.2.2.2'

$.connect(user+'@'+host1) 
$top -b -n1
save(host1, $.stdout)
#⬇ If you do not $.close() this connection.
#⬇ The next $.connect would be a nested ssh.
#⬇ You are ssh to host2 from host1, not from the localhost.
#$.close() 

pkey = $.pkey('/home/user/.ssh/id_rsa')
$.connect(user+'@'+host2,pkey=pkey)
$top -b -n1
save(host2, $.stdout)
$.close()
```

The next example below is also a scenario of nested ssh.

```python
def save(hostname, content):
    with open(f'{hostname}.top') as fd:
        fd.write($.stdout)

user = 'pauline'
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

For security reason, you could use key file in the localhost, and the key file in the host1 could be removed. For example:

```python
def save(hostname, content):
    with open(f'{hostname}.top') as fd:
        fd.write($.stdout)

user = 'george'
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

This function downloads a file from the remote host.

- src(str): remote file path to download, should be in absolute path
- dst(str): optional, local path to save the file
    - If the dst is a relative path,  os.path.abspath() would be called to get its absolute path.
    - The dst could be a folder. The downloaded filename would be the same as the src.
    - If dst is None, file would be saved to the os.getcwd().
- Return: tuple (src, dst), where the dst is the evaluated path of downloaded file.

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

This function breaks the execution of SSHScript script.

```python
$uname -a

# MacOS has "Darwin" in the output of "uname"
# Let's stop the execution for all others.
if $.stdout.find('Darwin') == -1:
    $.exit()

# this command is only executing on MacOS
$rm -rf /Users/jobs
```

For example:

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

This function inserts content in another SSHScript file into place. 

- filepath(str): the path of a sshscript file.
    - The path could be absolute or relative to the current file which doing the including.

For example:

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

The b.spy could be inserted into a.spy as many times as you like. Also, in the b.spy, you can insert another file.

To prevent an infinite loop of cycling including. The max times of a file to be included is 100. If you know what you are doing. You can change it by setting os.environ[’MAX_INCLUDE’]. eg.

```python
os.environ['MAX_INCLUDE'] = 999
```

## $.panaroid(yes)

- yes(boolean): If True, raises a SSHScriptError if there is data received from stderr. Default is false.

## $.pkey(filepath)

This function returns a RSA key from a file path. This works in context of local and remote.

- filepath(str): file path of the RSA key.
- Returns: an instance of paramiko.pkey.PKey

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

## $.thread()

This is a wrapper function of threading.Thread(). Please use it to get an instance of Thread instead of calling threading.Thread().  [Here is an usage example.](https://iapyeh.github.io/sshscript/examples/ex-py_cui_threading)

## $.upload(src, dst, makedirs=0, overwrite=1)

- src(str): the file path in the localhost to upload.
    - if the value is a relative path, os.path.abspath() is applied.
- dst(str): the file path in remote host to save the uploaded file, must be a absolute path
- makedirs(boolean): optional, default is False.
    - if True, intermediate folders of the dst path would be created if necessary.
- overwrite(boolean): optional, default is True.
    - if True, the destination file would be overridden if it is already existed, otherwise raises a FileExistsError.
- Returns: tuple (src, dst)

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
💡 If you are not satisfied by the $.upload , you can use the $.sftp for better control.

</aside>
