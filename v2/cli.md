# SSHScript v2.0 CLI(Draft)

Last Updated on 2023/11/1

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

The SSHScript package includes a CLI named `sshscript`. It is installed with the SSHScript package. To check if it is available, open a terminal and type `sshscript`. If it is not available, check the `$PATH` environment variable. ([details](gettingstarted))

## sshscript [paths [paths ...]]
### Executing dollar-syntax scripts (.spy)

This is for executing python scripts written in dollar-syntax of the SSHScript.
For example:
```
## file: hello.spy
$hostname
print(f'localhost is named as "{$.stdout}"')
```

Then, execute the hello.spy in a shell console, like this:

```
$ sshscript hello.spy
```

You can run multiple .spy files too.

For example, suppose that you have another .spy file named "world.spy".
Then you can run it like this:
```
$ sshscript hello.spy world.spy
```

## sshscript --folder FOLDER
### Executing dollar-syntax scripts in a folder

You can put .spy files into a folder and use --folder to address them.
The next example runs test/hello.spy and test/world.spy. 
```
$ sshscript --folder test hello.spy world.spy
```

The next example runs all .spy files in the test folder.
```
$ sshscript --folder test
```

"glob" could be used too. For example:
```
$sshscript --folder unittest base.spy "b*.spy"
```
This would run unittest/base.spy, unittest/b1.spy, unittest/b2.spy. But uittest/a1.spy is excluded.

## sshscript \-\-run-order
### Ensuring the sequence of execution

Suppose you want to run .spy files in a folder, like this:

```
$sshscript --folder unittest base.spy "b*.spy"
```

Since all .spy files are executed one-by-one. You want to make sure the executing sequence is correct.

You can use the --run-order option. For example
```
$sshscript --run-order --folder unittest base.spy "b*.spy"
```

With this option, sshscript will not execute them, it just shows them in order of execution.

## sshscript --folder FOLDER --ext SSHSCRIPTEXT 
### Changing default .spy to your own extension

If .spy is what you want, you can specify your own extension.
The next example runs all .myspy files in the test folder.
```
$sshscript --unittest --ext .myspy
```

## sshscript  \-\-debug
### Finding problems

This would set the debuging level to logging.DEBUG (10).
```
$sshscript --debug hello.spy 
```

If you prefer more details, you can set debuging level to 8

```
$sshscript --debug 8 hello.spy 
```
Please note that, for level 8, the logging message contains all data sent to ssh channel.
Some credential information, such as passwords, could be included in logging messages.


## sshscript  \-\-script
### Knowning what is exactly executed by Python

With this option, the sshscript would not execute script files.
It would output the parsed and converted python script from those .spy files.
This is for debugging purposes.

```
$sshscript --script hello.spy 
# output is converted "regular python script" of hello.spy, no execution.
```

From SSHScript 2.0, You can run the output script too. For example:
```
$ sshscript --script hello.spy > hello-parsed.spy
```
Then
```
$ sshscript --script hello-parsed.spy
```
When the sshcript runs the hello-parsed.spy, it would not parse it again.

## sshscript \-\-verbose
### Checking the outputs on stdout and stderr

With this option, the sshscript would  dump stdout and stderr to console. 

```
$sshscript hello.spy --verbose
```

You can set the prefix of dumping lines for stdout or stderr:
For stdout, it is os.environ[’VERBOSE_STDOUT_PREFIX’] , default is 🟩▏.
For stderr, it is os.environ[’VERBOSE_STDERR_PREFIX’] , default is 🟨.


## _ _export_ _ = [str …]

When you have  many *.spy files to run. You can export local variables in a file to files after it. For example:

```
#content of file: 0.spy
import json, pickle

myfolder = os.path.dirname(__file__)

def saveToJson(obj,filename):
    # ⬇if the "myfolder" is not exported,
    # ⬇ declare that it is a global also works
    # global myfolder  
    filepath = os.path.join(myfolder,filename)
    with open(filepath,'w') as fd:
        json.dump(obj,fd)

def saveToPickle(obj,filename):
    filepath = os.path.join(myfolder,filename)
    with open(filepath,'w') as fd:
        pickle.dump(obj,fd)

# we have to export "myfolder" too
# because "myfolder" is used in "saveToJson".
__export__ = ['savetoJson','myfolder']
```

```
#content of file: 1.spy

# "saveToJson" is available in 1.spy because it is exported by 0.spy
saveToJson({'hello':'world'})

# But "saveToPickle" is undefined
try:
    saveToPickle({'hello':'world'})
except NameError:
    pass
```

```
# You can test above 0.spy and 1.spy by
$sshscript 0.spy 1.spy
```

## _ _export_ _ = ‘*’

When __export__  is ‘*’, then all locals() are exported. For example:

```
#content of file: 0.spy
import json, pickle

def saveToJson(obj,filename):
    filepath = os.path.join(os.path.dirname(__file__),filename)
    with open(filepath,'w') as fd:
        json.dump(obj,fd)

def saveToPickle(obj,filename):
    filepath = os.path.join(os.path.dirname(__file__),filename)
    with open(filepath,'w') as fd:
        pickle.dump(obj,fd)

__export__ = '*'  #⬅ look here
```

```
#content of file: 1.spy
# saveToJson is available
saveToJson({'hello':'world'})

# saveToPickle is available too.
saveToPickle({'hello':'world'})
```

```
# You can test above 0.spy and 1.spy by
$sshscript 0.spy 1.spy
```

The __export__ can help to organize files better. You can put utilization functions or common variables in 0.spy and use them from 1.spy to 9.spy.

## Single Session of Execution

If you run many files sequentially. They would run in a single ssh session. Which means that if it has ssh-connected to a remote host in 0.spy, then 1.spy would also run in the same remote host. For example:

```
#content of file: 0.spy
$hostname
print($.stdout) #⬅ would be the localhost

# let's connect to "host"
$.connect(’user@host’)

# Please note that 
# we do not __export__ anything at the end of 0.spy.
```

```
#content of file:1.spy
$hostname
print($.stdout) #⬅ would be the "host"
$.close()  #⬅ would close the connetion to "user@host"
```

```
# You can test above 0.spy and 0.spy by
$sshscript 0.spy 1.spy

```