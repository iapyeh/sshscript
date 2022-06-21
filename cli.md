# sshscript CLI

If you install the sshscript package by “pip install”. A CLI “sshcript” is also installed by the setuptools. To check it, please open a terminal and type “sshscript”[ENTER].

## sshscript [filepath …]

This is the classic way to execute a SSHScript-style python script. e.g.

Suppose that there is a hello.spy :

```python
#file: hello.spy
$hostname
print(f'hello, this is {$.stdout}')
```

You can run it by:

```python
# This would also dump stdout and stderr to screen
$sshscript hello.spy
```

If there is another world.spy, you can run both files by 

```python
$sshscript hello.spy world.spy
```

Suppose that you have many files, you can put them into the same folder, and run them all by 

```python
# hello.spy and world.spy are moved into folder "unittest"
$sshscript unittest
```

## sshscript **╌silent**

with --silent, you can prohibit the screen dump of stdout and stderr.

```python
# prohibit dumps stdout and stderr to terminal
$sshscript hello.spy --silent
```

In fact, this behavior is automatically turned-on when sys.stdout.isatty() is True. You can also specify os.environ[’VERBOSE’]=”1” or os.environ[’VERBOSE’]=”” to turn it on and off in your script to control it manually.

<aside>
💡 When dump of stdout and stderr is enabled, you can change the following two variables to change the prefix of every single line.
For stdout, it is os.environ[’VERBOSE_STDOUT_PREFIX’] , its default is ▏.
For stderr, it is os.environ[’VERBOSE_STDERR_PREFIX’] , its default is 🐞.

</aside>

## sshscript **╌run-order**

When there are many files to run, the execution order does matter, you can check it by 

```python
# this only shows a list of *.spy files, no execution.
$sshscript unittest --run-order
```

You would find that files in the same folder are simply sorted by “sort” of a string list. But you can change their order by specifying some file as an argument. e.g.

```python
# Suppose that in the unittest folder,
# we have files a0.spy, a1.spy and a2.spy.
# They are run in oder of: a0.spy, a1.spy and a2.spy
# If you run them in this way:
$sshscript unittest/a2.spy unittest
# They would run in oder of: a2.spy, a0.spy and a1.spy
# You can check it by:
$sshscript unittest/a2.spy unittest --run-order

# Suppose that in the unittest folder,
# we also have files b0.spy, b1.spy and b3.spy.
# This command:
$sshscript "unittest/b*" "unittest/a*"
# It would run files in order of:
# b0.spy, b1.spy , b2.spy, a0.spy, a1.spy, a2.spy.
# Because it puts the "unittest/b*" in front of the "unittest/a*".

# Please note the double-quote in the above command.
# If they are not double-quoted. For example:
$sshscript unittest/b*
# It would contain unittest/b.sh 
# when there is a b.sh in the unittest folder.
# Since shell would expand "b*" to all the files which are prefixed by "b".

```

## sshscript  **╌script**

With this argument, the sshscript would dump the converted script. No execution. This is helpful for debugging.

## sshscript  **╌**debug

With this argument, the sshscript would dump the executing script where there is exception raise during execution. Also the level of logger would be set to “DEBUG”.

## 

## _ _export_ _ = [str …]

When you have  many *.spy files to run. You can export local variables in a file to those files after it. For example:

```python
#file: 0.spy
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

```python
#file: 1.spy
# saveToJson is available
saveToJson({'hello':'world'})

# But saveToPickle is not available
try:
    saveToPickle({'hello':'world'})
except NameError:
    pass
```

```python
# the command to run
$sshscript 0.spy 1.spy

# or put 0.spy and 1.spy into the same folder, say "testFolder".
# then, run this command:
$sshscript testFolder
```

## _ _export_ _ = ‘*’

When __export__  is ‘*’, then all locals() are exported. For example:

```python
#file: 0.spy
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

```python
#file: 1.spy
# saveToJson is available
saveToJson({'hello':'world'})

# saveToPickle is available too.
saveToPickle({'hello':'world'})
```

The __export__ can help to organize files better. You can put utilization functions or common variables in 0.spy and use them from 1.spy to 9.spy.

## Unisession

If you run many files at once. They are run in the same ssh session. Which means that if it has connected to a ssh server in 0.spy, then 1.spy was run under the same context. For example:

```python
#file: 0.spy
$hostname
print($.stdout) #⬅ would be the localhost

# let's connect to "host"
$.open(’user@host’)

# Please note that 
# we do not __export__ anything at the end of 0.spy.
```

```python
#file:1.spy
$hostname
print($.stdout) #⬅ would be the "host"
$.close()  #⬅ would close the connetion to "user@host"
```

```python
# The command to run 0.spy and 1.spy:
$sshscript 0.spy 1.spy

```
