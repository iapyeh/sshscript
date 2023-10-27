# SSHScript v2.0 Recipes

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Execute commands: one-dollar ($)](#one-dolar)
* [Execute shell commands: two-dollars($$)](#two-dolars)
* [Invoke an interactive console: with-dollar(with $)](#with-dollar)

## 🔵 <a name="one-dollar"></a>Setup Logger
```
import logging
logger = logging.getLogger('mylogger')
## ... do whatever you want to do with the logger ...
import sshscript
sshscript.setupLogger(logger)
```


