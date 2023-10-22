# SSHScript v2.0 Stdout, Stderr and Exitcode(Draft)

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Outputs of One-Dollar Commands](#one-dollar)
* [Outputs of Two-Dollars Commands](#two-dollars)
* [Outputs of With-Dollar Commands](#with-dollar)

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

The values of $.stdout, $.stderr and $.exitcode are changed after each dollar command execution. This means that if you execute two dollar commands in a row, the values of these variables will be set to the results of the second command.


## 🔵 <a name="one-dollar"></a> Outputs of Two-Dollars Commands


When a two-dollars command is executed, the following variables are also available:

* $.stdout: The standard output of the command.
* $.stderr: The standard error of the command.
* $.exitcode: The exit code of the command.

One-dollar and two-dollar commands in SSHScript are similar in many ways, but there are a few key differences.

One-dollar commands are executed directly by the subprocess or the Paramiko, while two-dollar commands are executed indirectly in a shell by the subprocess or the Paramiko. This means that two-dollar commands may output additional information, such as shell prompts, and may also be affected by the values of os.environ.

Be careful when using two-dollar commands, as the output may be different from what you expect.
If you need to execute a command, consider using the one-dollar command instead of a two-dollars command. This will give you more control over the execution environment and make it easier to handle the output.

If you are using two-dollars commands in a macOS terminal, consider deleting os.environ['TERM_PROGRAM'] before executing the command. This will prevent the stdout from being filled with terminal control characters.

One-dollar commands are generally recommended for most cases. They are simpler to use and produce more predictable results.

Two-dollar commands should be used when you need to execute a command that requires a shell environment, such as a command that uses shell variables or a command that needs to be executed in a specific shell.