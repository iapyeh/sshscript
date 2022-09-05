<div style="text-align:right"><a href="./index">Index</a></div>

# Release Notes of v1.1.15


## New feature: Windows Powershell Support

SSHScript can now work with powershell on Windows. When sys.platform is “win32”, the default shell of two-dollars command and with-dollar command would be the powershell. The executable path is obtained by shutil.which(’pwsh’). For two-dollars command, it is 

```
shell = shutil.which('pwsh') + ' -noni -nol -ExecutionPolicy RemoteSigned'
```

For interactive with-dollar command, it is

```
shell = shutil.which('pwsh') + ' -i -nol -ExecutionPolicy RemoteSigned'
```

If it is not what you want, you can use #! at the first line to assign the execution shell. For example:

```
$$"""
#!c:\\Program Files\\PowerShell\\7\\pwsh.EXE
echo "hello world"
"""

```

## New feature: compose commands by r-string

You can now use r-string to create commands. The following is an example of setting encoding in powershell. The content inside @{} would not be evaluated as a python statement.

```
with $r"""
    $PSDefaultParameterValues = @{ '*:Encoding' = 'utf8' }
""" as _:
    pass
```

Please be noted that  execution results of  the same r-string command in one-dollar and two-dollars might be different. The reason is that two-dollars command and with-dollar command would invoke shell, the same command would behave differently depending on its execution context. For example:

```
# one-dollar command (on MacOS)
$r'echo a:\\b\\c'
assert $.stdout == 'a:\\b'

# two-dollars command (on zsh)
$$r'echo a:\\b\\c'
assert $.stdout == 'a:\x08'

# with-dollar command (on zsh)
with $r'echo a:\\b\\c' as _:
    pass
assert $.stdout == 'a:\x08'

# two-dollars command (on bash)
$$r'''#!/bin/bash
    echo a:\\b\\c
'''
assert $.stdout.strip() == 'a:\\b\\c'

```

Just like using f-string to create commands, please do not mix r-strings with regular strings. When using r-strings to create commands, please use it to create the command at all. For example:

```
a = 'hello world'

# don't do this:
# mixing r-string and regular string 
$echo r'@{a}'

# instead, do it like this
$r'echo @{a}'
```

## New feature: os.environ[’SSH_CMD_INTERVAL’]

Now you can assign execution intervals for local executions and remote executions individually. The following example shows the difference.

```
# The interval between requests to site-1 and site-2 is 0.5 second
os.environ['CMD_INTERVAL'] = '0.5'
$'''
   curl https://site-1.com
   curl https://site-2.com
'''

# make a ssh connection to remote-host
$.connect('user@remote-host')

# The interval between requests to site-1 and site-2 is 1 second
os.environ['SSH_CMD_INTERVAL'] = '1'
$'''
   curl https://site-1.com
   curl https://site-2.com
'''
```

The default value is 0.5. 

For slow machines or slow connections, CMD_INTERVAL and SSH_CMD_INTERVAL might be critical. If you experienced WinError 258 (WAIT_TIMEOUT), you could try to tune up these values.

## bug-fixing:

The issue that fails to evaluate $.stdout in string like `a="'{$.stdout.strip()}'"` (double-quoted single quote) has been solved.

## Refine: console.sendline(list)

The sendline() now accepts multiple commands in the string list for the first argument. So you can send three kinds of commands: a string, a multi-lines string and a list of single-line strings. For example:

```
with $ as console:
    
    # kind 1:
    console.sendline('echo hello')
    
    # kind 2:
    # every line would be lstrip() before sending.
    console.sendline('''echo hello
                        echo world''')
    # kind 3:
    console.sendline(['echo hello','echo world'])

```

## Refine: \$\.download() and \$\.upload() behavior changed

Before v1.1.15, calling \$.download(src,dst) failed when the “src” was not an absolute path. As well as calling \$.upload(src,dst) failed when the “dst” was not an absolute path. Now, they trigger warnings only. There is no exception. You can suppress warnings by setting os.environ[’MUTE_WARNING’]=’1’

## Refine: \$\.paranoid() → \$\.careful()

The \$.paranoid() is renamed to \$.careful(). Due to “paranoid” might be a negative term. When $.careful(1) was called, the execution would be stopped if there is any \$.exitcode > 0. Starting from v1.1.15, the $.careful(1) is regardless of $.stderr. It is based on the value of \$.exitcode. So it works only when the \$.exitcode works.
