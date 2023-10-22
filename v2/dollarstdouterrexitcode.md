# SSHScript v2.0 Stdout, Stderr and Exitcode(Draft)

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [$.stdout](#dollar-stdout)
* [$.stderr](#dollar-stderr)
* [$.exitcode](#dollar-exitcode)

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
