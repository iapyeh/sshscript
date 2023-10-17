<div style="text-align:right"><a href="./index">Index</a></div>

# sshscript CLI

If you install the sshscript package by “pip install”. A CLI “sshcript” is also installed by the setuptools. To check it, please open a terminal then type “sshscript[ENTER]”.

## sshscript [filepath …]

This is the typical method to execute a sshscript-style python script. e.g.

Suppose that we have is a file named hello.spy :

```python
#content of hello.spy
$hostname
print(f'hello, this is {$.stdout}')
```

You can run the hello.spy in console by:

```python
$sshscript hello.spy
```

Suppose that there is another file named world.spy, you can run both by: 

```python
$sshscript hello.spy world.spy
```

If you have many files to run, you can put them into a folder, and run them all by:

```python
# there are many files like hello.spy and world.spy in the folder "unittest"
$sshscript unittest
```

## sshscript  \-\-debug

```
$sshscript hello.spy --debug
```

With this argument, the sshscript would dump the executing script where there is exception raise during execution. Also the level of logger would be set to “DEBUG”. 

## sshscript \-\-folder

With the argument, the sshscript will find files under the given folder.

```
# before
$sshscript unittest/0.spy unittest/1.spy unittest/2.spy  "unittest/b*.spy"

# starting from v1.1.14
$sshscript --folder unittest 0.spy 1.spy 2.spy "b*.spy"
```

## sshscript \-\-run-order

When many files are running sequentially, there execution order matters, you can check the running order by

```
$sshscript unittest --run-order
# this option would shows the running order of files, no execution.
```

The running order is simply a string-sorting result of filenames. If some file has to be the first file, you can specify it explicitly.

```
# Suppose that in the unittest folder,
# There are files a0.spy, a1.spy and a2.spy.
# Normally, they run in oder of: a0.spy, a1.spy and a2.spy

# When the a2.spy has to be the 1st to run:
$sshscript unittest/a2.spy unittest

# You can check the running order by:
$sshscript unittest/a2.spy unittest --run-order

# Suppose that in the unittest folder,
# There are files a0.spy, a1.spy and a2.spy.
# as well as b0.spy, b1.spy and b2.spy.
# Normally, they run in order of: a0,a1,a2,b0,b1,b2.spy

# When b-series have to run before a-series:
$sshscript "unittest/b*" "unittest/a*"

# Please note the double-quote is necessary in the above command.
# If they are not double-quoted. For example:
$sshscript unittest/b*
# It might be expanded to all files with prefix "b", eg. "b.sh", by shell.

```

A usage senario:

```
# Support in the unittest folder,
# File 0.spy would ssh to a remote server 
# File a0.spy, a1.spy are testing files for Feature-A
# File b0.spy, b1.spy are testing files for Feature-B

# Then, would doing testing of Feature-A on remote server
$sshscript unittest/0.spy "unittest/a*"

# Then, would doing testing of Feature-B on remote server
$sshscript unittest/0.spy "unittest/b*"
```

## sshscript  \-\-**script**

With this argument, the sshscript would dump the converted script. No execution. This is helpful for debugging.

```
$sshscript hello.spy --script
# output is converted "regular python script" of hello.spy, no execution.
```

When --script applies to many .spy files, the line numbers are continuously from the first file to the last one. Now if --script and --debug appear together, the line numbers are reset for every file. This would be more convenient for tracing codes according to traceback information.

```
# line numbering are different between the next 2 commends
$ sshscript 1.spy 2.spy --script
$ sshscript 1.spy 2.spy --script --debug
```

## sshscript \-\-**verbose**

With this argument, the sshscript would  dump stdout and stderr to console. 

```
$sshscript hello.spy --verbose
```

You can set the prefix of dumping lines for stdout or stderr:
For stdout, it is os.environ[’VERBOSE_STDOUT_PREFIX’] , default is ▏.
For stderr, it is os.environ[’VERBOSE_STDERR_PREFIX’] , default is 🐞.

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
