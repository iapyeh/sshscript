<div style="text-align:right"><a href="./index">Examples</a></div>

# Logger

## How to log in .spy

File: example.spy

```

from logging import DEBUG

$date

# in a .spy file, "logger" is directly accessible
$.log(DEBUG,f'now is {$.stdout.strip()}')
```

Execution

```
sshscript example.spy --debug
```

### Customizing with $.logger

For customizing logger, do it like this 

```
from logging import INFO, Formatter

# in a .spy file, "logger" is directly accessible
$.logger.setLevel(INFO)

# uncomment the next line to set formatter
#$.logger.handlers[0].setFormatter(Formatter('[HAPPY]:%(message)s'))

# execute command and do logging
$date
$.log(INFO,f'now is {$.stdout.strip()}')
```

Execution

```
# note: there is no \-\-debug argument
$sshscript example.spy 

```

## Using custom logger in a .py file(example 1)

File: example.py

```
from logging import DEBUG, Formatter
import logging,sys

# make a custom logger and handler
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('[HAPPY]:%(message)s')) 
logger = logging.getLogger('mylogger')
logger.addHandler(handler)
logger.setLevel(INFO)

# set it to be sshscript's logger
from sshscript import runScript, runFile, setupLogger
setupLogger(logger)

# a block of .spy script
runScript('''
    from logging import INFO
    $date
    $.log(INFO,f'now is {$.stdout.strip()}')
''')

# a .spy file
runFile('test.spy')
```

File: test.spy

```
from logging import INFO
$date
$.log(INFO,f'now is {$.stdout.strip()}')
```

Execution

```
python3 example.py
```

## Using custom logger in a .py file (example2)

File: example.py

```
from logging import DEBUG, INFO, WARN, ERROR, Formatter
import logging,sys

# make a custom logger and handler
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('[HAPPY]:%(message)s')) 
logger = logging.getLogger('mylogger')
logger.addHandler(handler)
logger.setLevel(INFO)

# set it to be sshscript's logger
from sshscript import setupLogger, SSHScript
setupLogger(logger)

# create an instance of SSHScript
session = SSHScript()

session.run('''
    $.connect('timwang@rms3')
''')    

# re-use this session
session.run('''
    $hostname
    $.log(INFO,f'hostname is {$.stdout.strip()}')
''',{'INFO':INFO})

session.close()
```

Execution

```
python3 example.py
```
