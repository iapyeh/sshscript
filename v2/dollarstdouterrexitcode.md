# SSHScript v2.0 Stdout, Stderr and Exitcode(Draft)

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [$.stdout](#dollar-stdout)
* [$.stderr](#dollar-stderr)
* [$.exitcode](#dollar-exitcode)

## 🔵 <a name="dollar-stdout"></a>$.stdout, $.stderr and $.exitcode

When a dollar command is executed, $.stdout has its output of stdout,
$.stderr has its output of stderr and $.exitcode has its exit code.

In the following example, $.stdout has the stdout output of "ls -l" command.
```
$ls -l 
for line in $.stdout.splitlines():
    print(line)
```

In the following example, $.stderr has the stderr output of "ls -l /non-existing" command.
```
$ls -l /non-existing
print('error: ' + $.stderr)
```

You can use $.exitcode to tell execution status

```
import random
if random.random() > 0.5:
    command = 'ls -l /non-existing'
else:
    command = 'ls -l '
$f'{command}'
if $.exitcode == 0:
    for line in $.stdout.splitlines():
        print(line)
else:
    print('error: ' + $.stderr)
```
