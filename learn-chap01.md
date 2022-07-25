<div style="text-align:right"><a href="./index">Index</a></div>

# Learning SSHScript Chapter 1

The SSHScript is in pure Python. Its capability is based on the [Paramiko](https://www.paramiko.org/) and subprocess. The SSHScript provides easy syntax for you. With the SSHScript you can embed shell commands in Python codes. It looks like writing a shell script in Python.

## Installation

Installation for your account only:

```
$pip install sshscript
or
$python3 -m pip install sshscript
```

Installation for all accounts on the same host:

```
$sudo pip install sshscript
or
$sudo python3 -m pip install sshscript
```

## Upgrading

Append  --upgrade at the end, eg.

```
$pip install sshscript --upgrade
```

Because the SSHScript is under development, you might need to upgrade sometimes.

## Check Installation

The lesson needs “sshscript” executable, let us check if it works before moving on. To check it, please type “sshcript [ENTER]” on your console.

```
$ sshscript
```

If your screen is something like below, you have done. (version number does not matter)

```
SSHScript Version:1.102
usage: sshscript [-h] [--run-order] [--script]...

SSHScript

positional arguments:
  paths               path of .spy files or folders

optional arguments:
  -h, --help          show this help message and exit
  --run-order         show the files to run in order...
  --script            show the converted python scri...
...
```

## Usage Scenario

1. Edit a file in python script (with suffix .spy) which contains statements in SSHScript syntax. Then execute the sshscript to run your .spy script.
2. Import sshscript module in a regular .py file, then call the sshscript.runFile() or sshscript.runScript() to run scripts which contain SSHScript syntax.

This lesson introduces Scenario 1. When you are familiar with Scenario 1, you are able to use the SSHScript in Scenario 2.

## Hello World

Below is a chunk of Python script with SSHScript syntax. Let's name it “hello.spy”.

```
# File content of the hello.spy
$ echo hello world
print($.stdout)
```

Run it from console by:

```
# On console, types "sshscript hello.spy"
$ sshscript hello.spy

# Output in console
hello world
```

If you are interested of the converted “regular” Python script, you can do it by:

```
# On console
$ sshscript hello.spy --script
# Output
001:try:
002:    __b = """echo hello world """
003:    __c = SSHScriptDollar(None,__b,locals(),globals(),inWith=0)
004:    __ret = __c(0)
005:finally:
006:    _c = __c
007:print(_c.stdout)
008:
```

It is not easy to understand. But you don’t need to. It is only useful in case of debugging. When you want to know the content of some line which was complained about in the traceback message.

Please be noted that only one line in the script:

```
$echo hello world
```

The SSHScript runs it and puts its stdout into the $.stdout. You can take the $.stdout as a regular variable. Just likes as the second line:

```
print($.stdout) 
```

It’s a regular Python script but prints a SSHScript-specific variable $.stdout. Let’s know more about the $.stdout.

## $.stdout

Please be noted that there is a dot (.) behind the $.

$.stdout is a str variable. Its content is the output of stdout of the least shell command. eg.

```
$echo hello world
assert $.stdout.strip() == 'hello world'
```

Since the “echo” outputs ”hello word” to stdout. The content of $.stdout is “hello world\n”（with newline）. Because it is a str，appending .strip() or other string functions are fine. eg.

```
$ls -l 
for line in $.stdout.split('\n'):
    cols = line.split()
    if len(cols): print('filename=',cols[-1])
```

## $.stderr

Please be noted that there is a dot (.) behind the $.

$.stdout is paired with $.stderr。The $.stdout is a str variable. Its content is the output of stderr of the least shell command.  eg.

```
# Content of stderr-testing.spy file
$ls -l /not-found-folder
print('Error:' + $.stderr) 
```

```
# In console
$ sshscript stderr-testing.spy

#Output：
Error: ls: /not-found-folder: No such file or directory
```

Generally speaking, $.stderr is an empty string if the least shell command execution is successful. But it is not always so, for example, the “sudo” outputs its prompt “Password:” from stderr. 

## Hello World @Host

All the example codes on the above sections are run on [localhost](http://localhost) by subprocess package. What if you want to execute them on a remote host?

All you have to do is connecting the remote host by adding one line:

```
$.connect('yourname@host',password='password')
$ echo hello world
print($.stdout)
```

When you have two hosts, you can do it by:

```
# ssh to host-a
$.connect('yourname@host-a',password='password-a')
$ echo hello world @host-a
print($.stdout)
$.close() # disconnect from host-a

# ssh to host-b
$.connect('yourname@host-b',password='password-b')
$ echo hello world @host-b
print($.stdout)
$.close() # disconnect from host-b. this line is optional
```

In case that the host-b is behind the host-a. You have to take the host-a as a bridge to the host-b. It’s easy, just keep the connection to the host-a, don’t close it, then connect to host-b. Here you are:

```
$.connect('yourname@host-a',password='password-a')
$.connect('yourname@host-b',password='password-b')
$ echo hello world
print($.stdout)
```

Usually, it is called “nested ssh”. With the SSHScript, you have done it with only 2 lines.

Of course, you can execute any commands.

```
$.connect('yourname@host-a',password='password-a')
$.connect('yourname@host-b',password='password-b')

# download file from host-b
$.download('/var/log/message')

# chekc disk uitilization
$ df
print($.stdout)

# check network connections
$ nestat -antu
print($.stdout)

# check who have been login this host
$ last -30
print($.stdout)
```

Or do some complex parsing on command’s output with Python

```
$.connect('yourname@host-a',password='password-a')
$.connect('yourname@host-b',password='password-b')

# Assume that you have a function to send SMS.
import sendsms

# Check the disk uitilizaion, and
# send a SMS　notification if the utilization over 80%
$ df
for line in $.stdout.split('\n'):
    cols = line.strip().split()
    if len(cols) and cols[4][-1] == '%':
          capacity = int(cols[4][:-1])
          if capacity > 80:
              sendsms(f'Warning:{cols[0]} has capacity over 80')
```

Actually, a .spy is a .py. You are full-powered by Python in a .spy too.

The $.connect() supports “with” syntax. You can utilize this feature to make codes more readable. eg.

```
with $.connect('yourname@host-a',password='password-a') as _:
    with $.connect('yourname@host-b',password='password-b') as _:
        $ echo hello world
        print($.stdout)
```

## ssh with key

If you do ssh with key, you can make connection without password by:

```
$.connect('yourname@host-a')
```

It is because the Paramiko would load the key from a regular path. At least it works on my Macbook Pro. If It was not working for you, you can explicitly assign the key, eg.

```
keypath = os.path.expanduser('~/.ssh/id_rsa')
# $.pkey() loads ssh key from file
$.connect('yourname@host-a',pkey=$.pkey(keypath))
```

When jumping to a nested host by ssh with key, the pkey parameter is required.

```
$.connect('yourname@host-a')

# Please be noted that the keypath is on the host-a, not on the localhost.
keypath = '/home/yourname/.ssh/id_rsa'
pkey = $.pkey(keypath)

$.connect('yourname@host-b',pkey=pkey)
```

If you have already moved the key file from the host-a to the localhost. You should load the key file before connecting to the host-a. eg.

```
keyA = $.pkey('keys/host-a/id_rsa')
keyB = $.pkey('keys/host-b/id_rsa')
$.connect('yourname@host-a',pkey=keyA)
$.connect('yourname@host-b',pkey=keyB)
```

The reason is that the $.pkey() loads the file depending on its context. Under the context of existing ssh connection, it looks for content on the connecting host instead of the local host.

## Many commands to run

If you have many commands to run, you can write them into a triple quotes string. eg.

```
$'''
df
netstat -antu
last -30
'''
```

Each line would be executed one by one, not in parallel. Their output would be collected together in $.stdout and $.stderr. As the given example code above, there are three instances of subprocess.Popen() being created for the three lines of command. The next chapter would introduce another syntax which runs the 3 commands in a single subprocess.