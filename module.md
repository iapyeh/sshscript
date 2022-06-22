<div style="text-align:right"><a href="./index">Index</a></div>
# sshscript module

You can import sshscript in regular python script. For example:

```python
import sshscript
paths = []
for filename in os.listdir('my-project'):
    if filename.endswith('.spy'):
        paths.append('my-project/'+filename)
sshscript.runFile(paths)
```

## sshscript.runFile()

This function executes .spy files, it has following parameters:

- paths: a file path(str) or a list of file path, this is required. List items could be path of file, folder or wildcard. You can find more details in the “[sshscript CLI](https://www.notion.so/sshscript-CLI-15576bb54f5d45cca7860e26caea0612)”.
- varGlobals: a dict to update the globals(), the default is None.
- varLocals: a dict to update the locals(), the default is None.
- showScript: if True, show converted script. No execution. The default is False.
- showRunOrder: if True, show files in order of running. No execution. The default is False.
- unisession: if True, run all files in a single session. If False, run every file in a new session. The default is True.

```python
import sshscript
sshscript.runFile('0.spy')
sshscript.runFile('a*.spy')
sshscript.runFile('/home/myproject/')
sshscript.runFile(['0.spy','1.spy']，None,locals())
```

## sshscript.runScript()

This function executes .spy script, it has following parameters:

- script: string of SSHScript script to execute. This is required.
- varGlobals: a dict to update to the glocals(), the default is None.
- varLocals:  a dict to update the locals(), the default is None.

```python
import sshscript

username = 'tim'
def say(hostname):
    print('hostname:', hostname)

script= '''
   $.open(f'{username}@host') #⬅ "username" is available
   $hostname
   say($.stdout) #⬅ "say" is available
   '''
sshscript.runScript(script,globals(),locals())
```

## Logger

You can get the logger of sshscript by 

```python
import logging
logger=logging.getLogger('sshscript')
```

or 

```python
import __main__
logger = __main__.logger
```

If you need to know the details about what the sshscript is working, please set the logging to debug level.

```python
import logging
logger.setLevel(logging.DEBUG)
```

If you want to log to file, below is an example:

```python
import __main__
logger = __main__.logger
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('unittest.log', 'w', 'utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s: %(message)s',"%Y-%m-%d %H:%M:%S")) 
logger.addHandler(handler)
```
