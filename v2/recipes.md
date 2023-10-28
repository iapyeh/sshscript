# SSHScript v2.0 Recipes

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Setup Logger](#setuplogger)
* [Using argparser in .spy](#argparser)

## 🔵 <a name="setuplogger"></a>Setup Logger
```
import logging
logger = logging.getLogger('mylogger')
## ... do whatever you want to do with the logger ...
import sshscript
sshscript.setupLogger(logger)
```
## 🔵 <a name="argparser"></a>Using argparser in .spy
```
## filename: example.spy
## run: sshscript example.spy --file myfile1.jpg
import argparse, __main__
parser = argparse.ArgumentParser()
parser.add_argument('--file', dest='file')
args = parser.parse_args(__main__.unknown_args)
print(args.file)
```