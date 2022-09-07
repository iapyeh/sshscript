<div style="text-align:right"><a href="./index">Index</a></div>

# Syntax, Variables and Functions

**for version 1.1.14**

![image](https://user-images.githubusercontent.com/4695577/186702052-d013bdbb-20ee-4b37-aac6-f38cea4cff43.png)

**for version 1.1.16**

# Syntax

## $

This defines a one-dollar command, it runs a single-line command.

- When not connecting to a remote host, run the command on [localhost](http://localhost) by subprocess.
- When connected to a remote host, run the command on the remote host by Paramiko’s API.

```
# example 1, run "ls -l" on localhost
$ls -l

# example 2, run "ls -l" on a remote host
$.connect('user@remote')
$ls -l
```

You can put python statements inside @{} or use f-string to define a command.

```

cmd = 'ls'
path = '/root'

$@{cmd} -l @{path}

# the above is evaluated to 
$ls -l /root

# you can also use f-string or r-string to assign the command
$f'{cmd} -l {path}

# when using f-string, use it to define the command at all.
# don't mix them like below: 
$ls -l f'{path}'
$@{cmd} -l f'{path}'
# Both yield unpredictable results.
# This rule also applies to commands in r-string.
```

You can get the command’s exit code by $.exitcode.

You can also get the command output by \$.stdout and $.stderr.

```
$[ -e /non-existing-file ]
assert $.exitcode == 1

$ls -l /tmp
lines = $.stdout.splitlines()
```

## $”””

This defines a multiple line one-dollar command. Single quote or double quote does not matter. For example:

```jsx

# suppose that you have three commands to run.
$ls -l /tmp
$whoami
$hostname

```

You can define a multiple line one-dollar command to put them together as follows: 

```jsx
$"""
    ls -l /tmp
    whoami
    hostname
"""

```

Every single line is executed individually. Their output of stdout or stderr are concatenated together. Commands are executed one after one. The value of $.exitcode is the exit code of the last command.

## $$

This defines a two-dollars command. Two-dollars commands will be executed in a shell. If your commands require it to run by a shell, you should use the two-dollars command. For example:

```jsx
$$ echo “1234” | sudo -S rm -rf /goodbye-root
```

Because the “sudo” requires a “pty” to work. The other usage scenario is that the environment works only in shell mode. For example:

```jsx
# You will get the value of $SHELL. 
$$ echo $SHELL

# The above command does not work if it is in a one-dollar command,
$echo $PATH
assert $.stdout.strip() == $SHELL
# the output is "$PATH", not the value of $SHELL

```

Inline commands also require a shell to work.

```jsx
# `pwd` works only in $$ not in $.
$$ echo `pwd` 
```

## $$”””

This defines a multiple line two-dollars command. Many commands can be put together, for example:

```jsx
$$"""
    cd /tmp
    ls -l
"""
# the output is file list of /tmp
```

These commands are executed in a single session of the shell. Their output of stdout or stderr are concatenated in $.stdout and $.stderr respectively. The example code below shows the difference between one-dollar and two-dollars commands.

```
# this is a one-dollar command
$'''
    cd /tmp
    ls -l
'''
# its output is not file list of /tmp, 
# because "cd /tmp" and "ls -l" are executed seperately.
```

You can assign  the shell which runs the two-dollar command by prefixing #! to its first line. For example:

```
$$"""
    #!/bin/sh -exu
    echo the shell is $0
    cd /var/log
    ls message
"""
# Notes: leading empty line and heading-spaces are ignored for readability,
# so #!/bin/sh is actually at the first line.
```

## with $$

This defines a with-command. By with-command, you can invoke an interactive console. 

```
with $$ as console:
    console.send('sudo -S su')
    console.expect('password') # case-insensitive 
    console.sendline('''root-password
          whoami
          cd /root
          tar -zcf root.backup.tgz ./
    ''')
    print(console.stdout)
    print(console.stderr)

```

### Alias styles:

Initially, the with-command is simply prefixing a “with” to a two-dollars command. Which means to open an interactive shell. Since the “with” is a strong hint, it does not matter how many dollars is following it. So, you can also prefix a “with” to a one-dollar command to define a with-command. The result is that any of the following styles defines a with-command:

- with $
- with $$
- with $ single line command
- with $$ single line command
- with $f”single line f-strting command”
- with $r”single line r-strting command”
- with $$f”single line f-strting command”
- with $$r”single line r-strting command”
- with $’’’ multiple line command ‘’’
- with $$’’’ multiple line command ‘’’
- with $f’’’ multiple line f-string command ‘’’
- with $r’’’ multiple line r-string command ‘’’

- with $$f’’’ multiple line f-string command ‘’’
- with $$r’’’ multiple line r-string command ‘’’

```
# a example of "with $"
with $sudo -S su as console:
    console.expect('password')
    console.sendline('''root-password
          whoami
    ''')

# a example of "with $$"
cmd = 'sudo -S su'
with $#!/bin/tcsh as console:
    console.sendline(cmd)
    console.expect('password')
    console.sendline('''root-password
          whoami
    ''')

# a example of "with $$-multiple-line", force to use /bin/bash
cmd = 'sudo -S su'
with $$'''
  $!/bin/bash
  PATH = /var/log:$PATH
  export PATH
	@{cmd}
''' as console:
    console.sendline('''root-password
          whoami
    ''')

# a example of "with $$-multiple-line f-string"
cmd = 'sudo -S su'
with $$f'''
  PATH = /var/log:$PATH
  export PATH
	{cmd}
''' as console:
    console.sendline('''root-password
          whoami
    ''')
```

### About the “console”

The “console” object has the following methods to use:

- sendline(command, waitingSeconds=1)
    - command: str, multi-lines str, list of single line str
        - command for inputing (ending newline is not necessary)
    
    ```
    with $ as console:
        console.sendline('''
            echo hello
            echo world
        ''')
        console.sendline(['echo hello','echo world'])
    ```
    
    - waitingSeconds: int, default is 1
        - seconds to wait after submitting the input string.
    
    ```python
    with $ as console:
        # at least wait 2 seconds before inputing password
        console.sendline('sudo -S lastb -F -10',2) 
        console.sendline('1234')
    print($.stdout)
    ```
    
- stdout
    - you can get the stdout output of the last executed command from this property.
- stderr
    
    you can get the stderr output of the last executed command from this property.
    
- expect(keyword, timeout=60)
    
    This function blocks the execution until the given keyword appears in stdout or stderr.
    
    - keyword: str, re.Pattern or list of both.
        - for example `console.expect([re.compile('pasword',re.I), 'SORRY'])`
        - for string, the matching is case insensitive
    - timeout: seconds to wait. If time is over, raises a TimeoutError.
    
    ```
    import re
    with $ as console:
        console.sendline('sudo -S lastb -F -10',2) 
    
        # wait for "password" to appear before inputing password
        console.expect('password')
        # another way is to set a string re.Pattern for expect()
        #console.expect(re.compile('PASSWORD',re.I))
    
        console.sendline('your-password')
    print($.stdout)
    ```
    
- expectStderr(keyword, timeout=60)
    
    same as expect() but only searching for stderr.
    
- expectStdout(keyword, timeout=60)
    
    same as expect() but only searching for stdout.
    

The with-command would be converted to a regular python “with .. as …” syntax. Of course, you don’t need to name it “console”.  Any name is fine. For example:

```
with $$ as slave:
   slave.sendline('whoami')
   slave.expect(['food','water','macpro'])
```

## @{python-code}  in command

You can embed python variables in one-dollar commands, two-dollars commands and with-commands. It would be evaluated before executing the command. For example:

```python
import datetime
now = datetime.datetime.now()
$tar -zcvf @{now.strftime("%m%d")}.tgz /var/log/system.@{now.strftime("%Y-%m-%d")} 

# if today is June 4, 1989. the command would be:
$tar -zcvf 64.tgz /var/log/system.1989-06-04
```

It also works in multiple lines commands:

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

You can get the output of dollar-commands (one-dollar or two-dollars commands) and with-command from $.stdout. If many commands are executed, the value of $.stdout would have all of them. For example:

```python
$"""
   echo "this is a book"
   echo "that is a pen"
"""
assert 'this is a book' in $.stdout
assert 'that is a pen'  in $.stdout
result = {
   'stdout': $.stdout,
   'stderr': $.stderr,
   'stdout+stderr': f'{$.stdout + $.stderr}'
}
```

Please be noted, when a shell is invoked, terminal control characters might be mixed in the value of $.stdout and $.stderr.

```python
$$"""
   echo "this is a book"
   echo "that is a pen"
"""
# the $.stdout would have many control characters.
```

For with-command, $.stdout is accessible when exiting the with block.

```
with $ as console:
    console.sendline('echo hello')
    # $.stdout has no value of "ls -l"
    # its value is in console.stdout
    assert 'hello' in console.stdout
    console.sendline('echo world')
# $.stdout contains stdout of all executions inside the with block.
assert 'hello' in $.stdout
assert 'world' in $.stdout

```

This is also valid for $.stderr.

## $.stderr

If  executions of dollars-commands  dump to stderr, you can get their content by $.stderr.

```python
$"""
cat /non-existing-file
"""
assert "No such file or directory" in $.stderr
```

There is a special note for $.stderr. Please consider three scenarios below:

- A: $cat /non-existed-file
- B: $$cat /non-existed-file
- C: with $$cat /non-existed-file

On localhost (subprocess), $.stderr would have value “No such file or directory” in A, B and C. But it is not the same when on a remote server.

On a remote server, scenario B and C do not dump to stderr. Instead, they dump it to stdout. This is a limitation. Please see the table at the bottom for a complete list of these limitations.

## $.client

The instance of paramiko.client.SSHClient of the current ssh session. If you know what you are doing, you can get the instance of paramiko.client.SSHClient for your own purpose. Before accessing this value, “$.connect()” should be called to open a ssh session.

## $.logger

For customizing the logger, previously, you have to get the logger from \_\_**main**\_\_.SSHScript.logger. For simplicity, you can now get the logger by $.logger.

```
import logging
handler = logging.FileHandler('unittest.log', 'w', 'utf-8')
$.logger.setLevel(logging.DEBUG)
$.logger.addHandler(handler)
```

Please see [this article for details](https://iapyeh.github.io/sshscript/examples/logger) about using the logger.

## $.sftp

If you know what you are doing, you can get the instance of paramiko.sftp_client.SFTP for your own purpose. Before accessing this value, “$.connect()” should be called to open a ssh session.

## os.environ

### os.environ[’CMD_INTERVAL’]

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

Default is 0.5 (seconds).

### os.environ[’CMD_TIMEOUT’]

The max time spent for executing a command in seconds.

Default is 60 seconds.

### os.environ[’MUTE_WARNING’]

This is used to suppress warnings when shell-specific characters (>&|;`) was found in a one-dollar command.  To enable it, please set its value to “1”.

Default is None. (False)

### os.environ[’SHELL’]

This is used when the subprocess is invoking shell. Usually it is set by your shell. You don’t need to bother it. If it is not set, shutil.which('bash') is called to find the shell to invoke.

No default value.

Note: starting from v1.1.14. you can force to use preferred shell and arguments by “#!” at the first line of a two-dollar command.

### os.environ[’SHELL_ARGUMENTS’]

This works with os.environ[’SHELL’]. When the sshscript gets shell value from os.environ[’SHELL’], it also gets arguments from os.environ[’SHELL_ARGUMENTS’].

No default value.

Note: starting from v1.1.14. you can force to use preferred shell and arguments by “#!” at the first line of a two-dollar command.

### os.environ[’SSH_CMD_INTERVAL’]

same as os.environ[’CMD_INTERVAL’] but for sending commands when connected on a remote host. For example:

```
os.environ[’SSH_CMD_INTERVAL’] = "2"
$.connect('user@hostname')
$$"""
    hostname
    cd /tmp
    pwd
"""
```

The default value is ‘0.5’. 

### os.environ[’VERBOSE]

The verbose mode is enabled by setting this value to non-empty string. When the verbose mode is enabled, every message received from stdout and stderr of the executing command would be shown on console.

You can enable it like this example:

```jsx
if sys.stdout.isatty():
    os.environ['VERBOSE'] = "1"
```

Default is “” (empty string), aka False

### os.environ[’VERBOSE_STDOUT_PREFIX’]

In verbose mode, This string is prefixed to every line when showing a messages of stdout on console.

Default is 🟩. (On powershell, default is “| ”)

### os.environ[’VERBOSE_STDERR_PREFIX’]

In verbose mode, This string is prefixed to every line when showing a messages of stderr on console.

Default is 🟨. (On powershell, default is “- ”)

## __main__

### __main__.SSHScript.logger

Sorry, this is no logger available in v1.1.14. Please get the logger by $.logger.

### __main__.unknown_args

The sshscript use argparse to parsing command-line arguments. It puts those unknown argements in __main__.unknown_args. You can use “argparse” in .spy file by parsing this variable. For example:

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

## $.break(code=0)

This function breaks the execution of the current executing script chunk. When you have many .spy files to run, the next file would start executing.

```python
$uname -a

# MacOS has "Darwin" in the output of "uname"
# Let's stop the execution for all others.
if $.stdout.find('Darwin') == -1:
    $.break()

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
    $.break()

$mysqladmin -uroot -p "@{args.password}" create girlfriends
```

## $.close()

This  function closes the current ssh connection. This is the counterpart of $.connect(). Please see examples in the $.connect() section. Actually, you don’t need to call this in the context of “with $.connect()”. But you do need this in some context.

## $.connect(host, username, password, port, policy,**kw)

This function opens a ssh connection to remote host.

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

- src(str): remote file path to download. If the src is not an absoulute path, a warning would be issued. You may set os.environ[’MUTE_WARNING’]=’1’ to suppress it.
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

## $.exit(code=0)

Starting from v1.1.14, $.exit() would end the main process of sshscript. The given code is the exit code. You can call $.exit(1) to indicate an error state of exiting.

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

## $.log(level, message)

This function writes logs for you. For example

```
from logging import WARNING
$[ -e /root/secret.txt ]
if $.exitcode == 0:
    $.log(WARNING,'too bad, root has its own secret')
```

Please see [this article for details](https://iapyeh.github.io/sshscript/examples/logger) about logging.

## $.careful(yes)

- yes(boolean): If True, raises a SSHScriptError if there is data received from stderr. Default is false.
- Previously named “$.paranoid()”. Renamed from v1.1.16.

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

This is a wrapper function of threading.Thread(). Please use it to get an instance of Thread in stead of calling threading.Thread().  [Here is an usage example.](https://iapyeh.github.io/sshscript/examples/ex-py_cui_threading)

## $.upload(src, dst, makedirs=0, overwrite=1)

- src(str): the file path in the localhost to upload.
    - If the value is a relative path, os.path.abspath() is applied.
- dst(str): the file path in remote host to save the uploaded file. If the dst is not an absoulute path, a warning would be issued. You may set os.environ[’MUTE_WARNING’]=’1’ to suppress it.
- makedirs(boolean): optional, default is False.
    - If True, intermediate folders of the dst path would be created if necessary.
    - When makedirs=1 is enabled, if the last component of the uploading destination has the same extension of the source file, the last component is taken as a file.
    
    ```
      # suppose "test.txt" is the file to upload
        
      src = 'test.txt'
      $.upload(src,'/tmp/non-exist1/non-exist2/test2.txt',makedirs=1)
        
      # the uploaded is /tmp/non-exist1/non-exist2/test2.txt
      # at version 1.1.12 and earlier, 
      # the uploaded is /tmp/non-exist1/non-exist2/test2.txt/test.txt
        
      # --- the next 3 calls in v1.1.14 are the same as in v1.1.12 ---
        
      $.upload(src,'/tmp/non-exist1/non-exist2/test.txt',makedirs=1)
      # uploaded is /tmp/non-exist1/non-exist2/test.txt
        
      $.upload(src,'/tmp/non-exist1/non-exist2',makedirs=1)
      # uploaded is /tmp/non-exist1/non-exist2/test.txt
        
      $.upload(src,'/tmp/non-exist1/non-exist2/test.jpg',makedirs=1)
      # uploaded is /tmp/non-exist1/non-exist2/test.jpg/test.txt
    ```
    
- overwrite(boolean): optional, default is True.
    - If True, the destination file would be overridden if it is already existed, otherwise raises a FileExistsError.
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

![Untitled](Syntax,%20Variables%20and%20Functions%209c002afd174b4691b052c31139754b02/Untitled.png)

![image](https://user-images.githubusercontent.com/4695577/186576710-baf846ac-b88c-4b23-9f9e-49ea00b909f0.png)
