# SSHScript v2.0 Upload and Download Files

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Upload : $.upload()](#dollar-upload)
* [Download : $.download()](#dollar-download)


## 🔵 <a name="dollar-upload"></a>Upload: $.upload()

### 🌎＄ Upload files to remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
import os
assert os.path.exists('image.jpg')
with $.connect('user@host','1234') as host:
    host.upload('image.jpg','imageuploaded.jpg')
    host('[ -e "$PWD"/imageuploaded.jpg ]')
    assert host.exitcode == 0
    ## move the uploaded file to /root
    with host.sudo('1234') as sudo:
        sudo('cp imageuploaded.jpg /root')
        sudo('[ -e /root/imageuploaded.jpg ]')
        assert sudo.exitcode == 0
```

### 🌎🐍 Upload files to remote host using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
import os
assert os.path.exists('image.jpg')
with session.connect('user@host','1234') as host:
    host.upload('image.jpg','imageuploaded.jpg')
    host('[ -e "$PWD"/imageuploaded.jpg ]')
    assert host.exitcode == 0
    ## move the uploaded file to /root
    with host.sudo('1234') as sudo:
        sudo('cp imageuploaded.jpg /root')
        sudo('[ -e /root/imageuploaded.jpg ]')
        assert sudo.exitcode == 0
```
## 🔵 <a name="dollar-download"></a>Download: $.download()

### 🌎＄ Download files from remote host using the SSHScript dollar-syntax
```
## filename: example.spy
## run: sshscript example.spy
import os
with $.connect('user@host','1234') as host:
    $[ -e "$PWD"/image.jpg ]
    assert $.exitcode == 0
    host.download('image.jpg','imagedownloaded.jpg')
## check downloaded file on localhost
$[ -e imagedownloaded.jpg ]
assert $.exitcode == 0
```

### 🌎🐍 Download files from remote host using the SSHScript module

```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
import os
with session.connect('user@host','1234') as host:
    ## check source file on remote host
    host('[ -e "$PWD"/image.jpg ]')
    assert host.exitcode == 0
    host.download('image.jpg','imagedownloaded.jpg')
## check downloaded file on localhost
session('[ -e imagedownloaded.jpg ]')
assert session.exitcode == 0
```

### Symbols

- ⏚ : local

- 🌎 : remote

- ＄ : SSHScript dollar-syntax

- 🐍  : SSHScript module