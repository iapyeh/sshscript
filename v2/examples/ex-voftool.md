<div style="text-align:right"><a href="./index">Back to Index</a></div>

## Backup VMGuest by "voftool"

```
## filename: exportvmguest.spy
vmHostIP = '1.2.3.4'
vmGuestId = 'WEB1'
ovafile = 'WEB1.ova'
cmd=f'/home/iap/ovftool --noSSLVerify vi://{vmHostIP}/{vmGuestId} {ovafile}'
username = 'root'
password = 'secret'
with $.shell():
    ## because "ovftool" would exit by itself, so set exit=False
    with $.enter(cmd,exit=False) as ovftool:
        ovftool.expect('Username')
        ovftool.input(username)
        ovftool.expect('Password')
        try:
            ovftool.input(password)
            ovftool.expect(['complete','success'],timeout=1800)
        except TimeoutError:
            print(['Error timeout'])
            ovftool.input(chr(3))
    if $.exitcode == 0:
        print(['OK',$.exitcode,$.stdout])
    else:
        print(['Error',$.exitcode,$.stdout,$.stderr])
print('finish')
```
#### Executing 
```
$sshscript exportvmguest.spy
```

## Backup VMGuest by "voftool" (python script)
```
## filename: exportvmguest.py
import sshscript
import os
os.environ['DEBUG'] = '1'
vmHostIP = '1.2.3.4'
vmGuestId = 'WEB1'
ovafile = 'WEB1.ova'
cmd=f'/home/iap/ovftool --noSSLVerify vi://{vmHostIP}/{vmGuestId} {ovafile}'
username = 'root'
password = 'secret'
session = sshscript.SSHScriptSession()
with session.shell() as console:
    ## because "ovftool" would exit by itself, so set exit=False
    with console.enter(cmd,exit=False) as ovftool:
        ovftool.expect('Username')
        ovftool.input(username)
        ovftool.expect('Password')
        try:
            ovftool.input(password)
            ovftool.expect(['complete','success'],timeout=1800)
        except TimeoutError:
            print(['Error timeout'])
            ovftool.input(chr(3))
    if console.exitcode == 0:
        print(['OK',ovftool.exitcode,ovftool.stdout])
    else:
        print(['Error',ovftool.exitcode,ovftool.stdout,ovftool.stderr])
```
### Executing 
```
$python3 exportvmguest.py
```
![image](https://user-images.githubusercontent.com/4695577/182324261-f6e0579c-df39-4e76-bbfe-00722200450c.png)
