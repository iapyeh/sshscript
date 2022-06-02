# SSHScript

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

## with $ , with $”””

An interactive shell. Commands are initial commands when the shell starts.

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
💡 with $$, with $$””” are all the same as with $

</aside>

## os.environ

### os.environ[’VERBOSE] = “1”

```jsx
if sys.stdout.isatty():
    os.environ['VERBOSE'] = "1"
```

### os.environ[’CMD_INTERVAL’] = “0.5”

The interval between two lines of command are default to 0.5 seconds after the latest time when having data received from stdout or stderr.  This value can be changed by os.environ[’CMD_INTERVAL’]. For example:

```jsx
os.environ[’CMD_INTERVAL’] = "0.1"
$${
    cd /tmp
    ls -l
}
```

The output of stdout or stderr are put together in $.stdout and $.stderr respectively.

Reset this value by

```jsx
del os.environ[’CMD_INTERVAL’]
```

## $.stdin, $.stdout, $.stderr in Py

## $.stderr

There is a special note for $.stderr. Please consider the example in 3 cases:

- A. $cat /non-existed-file
- B. $$cat /non-existed-file
- C. with $$cat /non-existed-file

For local subprocess, $.stderr would have value “No such file or directory” in A, B and C.

For remote ssh session, $.stderr would have value “No such file or directory” for A only. 

For remote ssh session, in case B and C, **$.stdout** would have the error message “No such file or directory”. Since this is the behavior of the paramiko invoke_shell() which implicitly set get_pty=True.

## $@{python-expression}  , $$@{python-expression}

## $.close()

## $.download(src-remote,dst-local)

## $.exit()

## $.getkey()

## $.include()

## $.open(username@host)

## $.open() , with

## $.open() , nested

## $.panaroid(boolean:)

## $.timeout(int:)

## $.upload(src-local,dst-remote,makedirs=0,overwrite=1)

## __export__ = [’name’,...]

## __export__ = [’*’]

## CLI

### [sshscript](http://sshscript.py) [file or folder]

### [sshscript](http://sshscript.py) [file or folder]  -- script
