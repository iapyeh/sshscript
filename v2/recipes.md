# SSHScript v2.0 Recipes

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Setup Logger](#setuplogger)
* [Using argparser in .spy](#argparser)
* [Working with the systemctl](#systemctl)

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
But this way, the content would be mixed with terminal control codes.
The following example is more practical:
```
with $.sudo(sudoPassword) as console:
    ## redirect the output of systemctl to a file
    console('systemctl --type=service --state=active > /tmp/crontab-root.txt')
    console('cat /tmp/crontab-root.txt')
    content = console.stdout
    console('rm -f /tmp/crontab-root.txt')
    print(content) 
```