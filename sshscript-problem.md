<div style="text-align:right"><a href="./index">Index</a></div>

# sshscript related problems

## Check the installation of sshscript (CLI)

SSHScript package has a CLI "sshscript". To check if it is successfully installed. You can open a console and type:

```
$ sshscript
```

If your screen is something like below, than the installation is succeeded. (regardless version)

```
usage: sshscript [-h] [--run-order] [--script]...(etc）

SSHScript

positional arguments:
  paths               path of .spy files or folders

optional arguments:
  -h, --help          show this help message and exit
  --run-order         show the files to run in order...
  --script            show the converted python scri...
(...etc...）

```

## What if installation was failed

### Case I：command not found

You can check if the installation path is in the $PATH by "which" command.

```
$ which sshscript
```

If the "which" can not find the path for "sshscript", you have to add the installation path into $PATH.

You might use this command to find crues of where it is:
```
$python3 -c "import sshscript;print(sshscript.__file__)"
```
Suppose its output is
```
/home/john/.local/lib/python3.9/site-packages/sshscript/__init__.py
```
the executable "sshscript" CLI might be 
```
/home/john/.local/bin/sshscript
```
Then, `/home/john/.local/bin` is the path which has to be added into the $PATH.

### Case II：Bad Interpreter

When you run `sshscript` and have result like this:
```
-bash: ... bad interpreter: No such file or directory
```
The reason is that the setuptools writes an incorrect path of the python executable when generating executables. The solution is simply to edit it.

For example, the 1st line of "sscript" might be:

```
#!/usr/local/bin/python
```

Because we got a "bad interpreter", which means that "/usr/local/bin/python" is invalid path of the python executable.

You might change it to be:

```
#!/usr/bin/env python3 
```

or you can find the absolute path of python3 by 
```
$python3 -c "import sys;print(sys.executable)"
```
suppose its output is
```
/home/john/workspace/local/bin/python3
```
then, you can change the first line of "sshcript" to be
```
#!/home/john/workspace/local/bin/python3
```


### Non of above cases:

You are welcome to issue a ticket on [the Github's issue system](https://github.com/iapyeh/sshscript/issues)
