# SSHScript v2.0 Stdout, Stderr and Exitcode(Draft)

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Outputs of One-Dollar Commands](#one-dollar)
* [Outputs of Two-Dollars Commands](#two-dollars)
* [Outputs of With-Dollar Commands](#with-dollar)
* [SSHScript Module](#sshscript-module)

## 🔵 <a name="one-dollar"></a> Outputs of One-Dollar Commands


When a one-dollar command is executed, the following variables are available:

* `$.stdout`: The standard output of the command.
* `$.stderr`: The standard error of the command.
* `$.exitcode`: The exit code of the command.

The following example prints the standard output of the `ls -l` command:

```
$ls -l 
for line in $.stdout.splitlines():
    print(line)
```

The following example prints the standard error of the `ls -l /non-existing` command:

```
$ls -l /non-existing
print('error: ' + $.stderr)
```

You can use `$.exitcode` to check the execution status of a command. For example, the following code prints the standard output of the command, or prints an error message if the command fails:

```
path = 'somepath'
$f'ls -l {path}'
if $.exitcode == 0:
    for line in $.stdout.splitlines():
        print(line)
else:
    print('error: ' + $.stderr)
```

**The values of $.stdout, $.stderr and $.exitcode are changed after each dollar command execution. This means that if you execute two dollar commands in a row, the values of these variables will be set to the results of the second command.**


## 🔵 <a name="two-dollars"></a> Outputs of Two-Dollars Commands

A two-dollar command can span multiple lines. Each line is executed as a separate command.

When a two-dollars command is executed, the following variables are also available:

* $.stdout: The standard output of all commands.
* $.stderr: The standard error of all commands.
* $.exitcode: The exit code of the last command.

One-dollar and two-dollar commands in SSHScript are similar in many ways, but there are a few key differences.

One-dollar commands are executed directly by the subprocess or the Paramiko, while two-dollar commands are executed indirectly in a shell by the subprocess or the Paramiko. This means that two-dollar commands may output additional information, such as shell prompts, and may also be affected by the values of os.environ.

Be careful when using two-dollar commands, as the output may be different from what you expect.
If you need to execute a command, consider using the one-dollar command instead of a two-dollars command. This will give you more control over the execution environment and make it easier to handle the output.

If you are using two-dollars commands in a macOS terminal, consider deleting os.environ['TERM_PROGRAM'] before executing the command. This will prevent the stdout from being filled with terminal control characters.

One-dollar commands are generally recommended for most cases. They are simpler to use and produce more predictable results.

Two-dollar commands should be used when you need to execute a command that requires a shell environment, such as a command that uses shell variables or a command that needs to be executed in a specific shell.

## 🔵 <a name="with-dollar"></a> Outputs of With-Dollar Commands

With-dollar commands in SSHScript invoke a shell process. When a with-dollar command is executed, the following variables are available:

* $.stdout: The standard output of the shell process.
* $.stderr: The standard error of the shell process.
* $.exitcode: The exit code of the shell process.

Inside the block of a with-dollar command, you can get the stdout, stderr, and exit code of the last command executed by the console object.

$.stdout is mixed with the standard output of the shell process.

This means that all output from the shell process is captured by $.stdout.

When a command is executed inside the with-block, you can read the output of the shell process as it is being produced by using the console.stdout and console.stderr properties.

For example
```
with $#!/bin/bash as console:
    console('hostname')
    print('hostname=',console.stdout.strip())
    print('exitcode of hostname=',console.exitcode)
    console('whoami')
    print('whoami=',console.stdout.strip())
    print('exitcode of whoami=',console.exitcode)
print('output of shell process=',$.stdout.strip())
print('exitcode of shell process=',$.exitcode)
```

Tips for Using With-Dollar Commands

* With-dollar commands can be useful for executing commands that require a shell environment, such as commands that use shell variables or commands that need to be executed in a specific shell.
* However, it is important to be aware that with-dollar commands can produce unexpected results, especially if the output of the shell process is not properly handled.
For example, if the shell process produces a lot of output, it can cause the SSHScript interpreter to run out of memory.
* To avoid problems, it is important to handle the output of with-dollar commands carefully. You might redirect the output to a file or consider using $.iterate().

## 🔵 <a name="sshscript-module"></a>SSHScript Module

The $.stdout, $.stderr, and $.exitcode can be accessed by the SSHScript session instance when working with SSHScript modules.

The SSHScript session instance is the object that you use to execute commands on the localhost or a remote host. To access the $.stdout, $.stderr, and $.exitcode properties, you can use the following code:

For example
```
import sshscript
session = sshscript.SSHScriptSession()

## session() is equivalent to one-dollar commands
session('hostname')
print('hostname=', session.stdout.strip())
print('exitcode=', session.exitcode)

## session(command,shell=True) is equivalent to two-dollars commands
session('echo $HOME', shell=True)
print('output=', session.stdout.strip())
print('exitcode=', session.exitcode)

## "with session.shell()" is equivalent to with-dollar commands
with session.shell('#!/bin/bash') as console:
    console('hostname')
    print('hostname=',console.stdout.strip())
    print('exitcode of hostname=',console.exitcode)
    console('whoami')
    print('whoami=',console.stdout.strip())
    print('exitcode of whoami=',console.exitcode)
print('output of shell process=',session.stdout.strip())
print('exitcode of shell process=',session.exitcode)

```
