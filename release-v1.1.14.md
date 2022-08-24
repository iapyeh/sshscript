<div style="text-align:right"><a href="./index">Index</a></div>

# Release Notes of v1.1.14

Summary

- New feature: $.exitcode
    
    ```jsx
    $[ -e /non-existing-file ]
    assert $.exitcode == 1
    ```
    
- New syntax:  commands in f-string
    
    ```
    # define "cmd"
    cmd = 'ls -l'
    
    # then, the next 3 lines are equivlent
    $@{cmd}
    
    $f'{cmd}'
    
    $f'''
       {cmd}
       '''
    ```
    
    Please be noted that if you use f-string for command, then make it completely with f-string. don’t mix them. For example:
    
    ```
    path = '/root'
    
    # this is valid, it will be 'ls -l /root'
    $f' ls -l {path}'
    
    # Don't mix string and f-string. the behavior is not defined
    $ ls -l f'{path}'
    ```
    
- Refine: initial command is no more required for with-command. That is to day, you can define a with-command by “with $ as” or “with $$ as” directly. For example:
    
    ```
    with $ as shell:
        shell.sendline('ls -l')
    
    with $$ as shell:
        shell.sendline('ls -l')
    ```
    
- New feature: assign shell by #!
    
    Before v1.1.14,  if you want to use your preferred shell for two-dollars and with-dollars commands. You have to set os.environ[’SHELL’] and os.environ[’SHELL_ARGUMENTS’].  now you can assign what shell and its arguments to use directly in the first line.
    
    ```
    # force to use /bin/tcsh
    with $#!/bin/tcsh as shell:
         shell.sendline('echo shell is $0')
    assert $.stdout == 'shell is /bin/tcsh'
    
    # force to use sh -eux
    with $#!/bin/sh -eux as shell:
       shell.sendline('echo shell is $0')
    assert $.stdout == 'shell is /bin/sh'
    
    # force to use bash
    $$'''
    	#!/usr/bin/env bash
    	cd /tmp
    	ls -l
    	'''
    
    # open an interactive session of python
    $$'''
    #!/usr/bin/env python3 -i
    import sys
    print('hello world')
    exit()
    '''
    ```
    
    The #! also gives a canonical method to get a root console. Eg.
    
    ```
    # this style is valid on both local and remote scenario
    with $#!/bin/bash as shell:
        shell.sendline('sudo -S su')
        shell.expect('password')
        shell.sendline(f'''{password}
            whoami
            echo shell is $0
        ''')
    ```
    
    There are many ways to get a root console. They are variants in local and remote scenarios. For details, please [see these example](https://iapyeh.github.io/sshscript/examples/root-console)s.
    
- New feature: sendline() can send multi-lines too.
    
    ```
    with $$ as shell:
        shell.sendline(f'''
            cd /tmp
            ls -l
        ''')
        shell.sendline('echo $?')
    ```
    
- New CLI argument: \-\-folder
    
    ```
    # before
    $sshscript unittest/0.spy unittest/1.spy unittest/2.spy  "unittest/b*.spy"
    # after
    $sshscript --folder unittest 0.spy 1.spy 2.spy "b.spy"
    ```
    
- New feature: $.log() and $.logger
    
    You can use $.log() to do logging and customize the logger with $.logger
    
    Please see [examples](https://iapyeh.github.io/sshscript/examples/logger) for detail.
    
- Refine: more sophisticated Scenarios of thread support
    - [Example 1](https://iapyeh.github.io/sshscript/examples/ex-threads-userlist)
    - [Example 2](https://iapyeh.github.io/sshscript/examples/ex-threads-userlist2)
- Refine: expect(list) returns matched item
    
    In the closure of a with-command, the “expect()” now returns the matched item.
    
    ```
    with $ as shell:
        shell.sendline('''sudo su''')
        matched = shell.expect(['username','password'],3)
        assert matched == 'password'
    ```
    

- Refine: \-\-script and  \-\-debug
    
    When \-\-script applies to many .spy files, the line numbers are continuously from the first file to the last one. Now if \-\-script and \-\-debug appear together, the line numbers are reset for every file. This would be more convenient for tracing codes according to traceback information.
    
    ```
    # line numbering are different between the next 2 lines
    $ sshscript bugy-script-1.spy bugy-script-2.spy --script
    $ sshscript bugy-script-1.spy bugy-script-2.spy --script --debug
    ```
    
- Refine: argument “makedirs=1” of $.upload() changes behavior
    
    Now, when makedirs=1 is enabled, if the last component of the uploading destination has the same extension of the source file, the last component is taken as a file. Previously, it was taken as a folder no matter what it is unless it is of the same filename as the source file.
    
    ```
    # suppose "test.txt" is the file to upload
    
    src = 'test.txt'
    $.upload(src,'/tmp/non-exist1/non-exist2/test2.txt',makedirs=1)
    
    # the uploaded is /tmp/non-exist1/non-exist2/test2.txt
    # at version 1.1.12 and earlier, 
    # the uploaded is /tmp/non-exist1/non-exist2/test2.txt/test.txt
    
    # --- the next 3 calls in v1.1.14 are the same as in v1.1.12 ---
    
    $.upload(src,'/tmp/non-exist1/non-exist2/test.txt',makedirs=1)
    # uploaded is /tmp/non-exist1/non-exist2/test.txt
    
    $.upload(src,'/tmp/non-exist1/non-exist2',makedirs=1)
    # uploaded is /tmp/non-exist1/non-exist2/test.txt
    
    $.upload(src,'/tmp/non-exist1/non-exist2/test.jpg',makedirs=1)
    # uploaded is /tmp/non-exist1/non-exist2/test.jpg/test.txt
    
    ```
    
- Refine: Prohibition of putting “|” in one-dollar command is removed.
    
    The v1.1.12 rejects to execute if shell-specific characters such as >, |, & was found in the command. This restriction was removed. Instead, it drops warnings. If you encountered this issue and didn't like it. Please disable the warning by this way:
    
    ```
    # disable warnings when one-dollar command contains >, < , |, & or ;
    os.environ['MUTE_WARNING'] = '1'
    ```
    
- Refine: $.exit() and $.break()
    
    In v1.1.12, $.exit() does not end the main process and return to shell. It is just to stop the execution of the current spy file and start to execute the next spy file. For better naming of functionality, from v1.1.14, $.exit() would really return to shell and $.break() will stop the execution of the current file and move to the next file (aka previously the $.exit() in v1.1.12). You can call $.exit(1) to indicate an error state of exiting.
    
- Refine: when the sshscript CLI is executed in a tty and there are no arguments. It will dump help and check if the installed version is the last version.
    
- bug-fixing: command interval control. This is an internal bug which was something like without throttle between commands. It leads to making the setting of os.environ[’CMD_INTERVAL’] in vain.
- bug-fixing: $.stdout in f-string
    
    This bug is that $.stdout and $.stderr were not evaluated to its value. In the next example, it was not working in v1.1.12. Now it works.
    

```
# execute a command
$data
# set its output to variable a by f-string
a = f'''
    stdout is {$.stdout}, 
    concatenation of stderr are {$.stdout + $.stderr}
    '''
```

- bug-fixing: command interval control. This is an internal bug which was something like without throttle between commands. It leads to making the setting of os.environ[’CMD_INTERVAL’] in vain.

![image](https://user-images.githubusercontent.com/4695577/186346811-f44a3059-952b-4db1-8954-25e5fb3a6215.png)
