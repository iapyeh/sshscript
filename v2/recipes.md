# SSHScript v2.0 Recipes

Last Updated on 2023/10/31

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Setup Logger](#setuplogger)
* [Using argparser in .spy](#argparser)
* [Working with the systemctl](#systemctl)
* [Get rid of terminal control codes](#getridterminalcodes)
* [Inputing password for mysqldump](#mysqldump)

## 🔵 <a name="setuplogger"></a>Setup Logger
```
import logging
logger = logging.getLogger('mylogger')
## ... do whatever you want to do with the logger ...
import sshscript
sshscript.setupLogger(logger)
```
## 🔵 <a name="argparser"></a>Using argparser in .spy
If you need to have your own cli-arguments, you can get them from __main__.unknown_args
```
## filename: example.spy
## run: sshscript example.spy --file myfile1.jpg
import argparse, __main__
parser = argparse.ArgumentParser()
parser.add_argument('--file', dest='file')
args = parser.parse_args(__main__.unknown_args)
print(args.file)
```
## 🔵 <a name="systemctl"></a>Working with the systemctl
This command "systemctl --type=service --state=active" displays content page by page, you can run it with $.enter.
Example:
```
import time    
with $.sudo(sudoPassword) as console:
    content = []
    ## press "q" to exit, otherwise this command will block at the bottom page
    with console.enter('systemctl --type=service --state=active',exit='q') as systemctlscreen:
        content.append(systemctlscreen.stdout)
        while 'END' not in systemctlscreen.stdout:
            systemctlscreen.input(' ') ## move to next page
            time.sleep(1) ## wait 1 second for screen to refresh
            content.append(systemctlscreen.stdout)
    print(content) 
```
But this way, the content might be mixed with terminal control codes.
The following example is more practical:
```
with $.sudo(sudoPassword) as console:
    ## redirect the output of systemctl to a file
    console('systemctl --type=service --state=active | cat')
    content = console.stdout
    print(content) 
```

## 🔵 <a name="getridterminalcodes"></a>Get rid of terminal control codes

Terminal control codes can be distracting when mixed with output. You can avoid this by modifying your command. 
```
## For example, instead of running:
with $.sudo(sudoPassword) as console:
    console('systemctl --type=service --state=active')

## You can run:
with $.sudo(sudoPassword) as console:
    console('systemctl --type=service --state=active | cat')
```
Some programs automatically add terminal control codes, such as `grep --color=auto`.
You can disable this by running the command with the `--color=never` option. 

```
## For example, instead of running:
with $.sudo(sudoPassword) as console:
    console('lsof -n -Pi | grep LISTEN')

## You can run:
with $.sudo(sudoPassword) as console:
    console('lsof -n -Pi | grep --color=never LISTEN')
```

This will prevent the program from adding any terminal control codes to the output.


## 🔵 <a name="mysqldump"></a>Inputing password for mysqldump
`mysqldump` requires password, so we could use $.enter to handle it. For example:

```
with $.enter(f'mysqldump -u root -p mydb > db.sql','password','1234',exit=False) as mysqldump:
    pass
```
or
```
with $.enter(f'mysqldump -u root -p mydb > db.sql',exit=False) as mysqldump:
    mysqldump.expect('password')
    mysqldump.input('1234')
```

Please note that you should set "exit=False" for $.enter, since `mysqldump` would stop by itself, exiting command is not necessary.
