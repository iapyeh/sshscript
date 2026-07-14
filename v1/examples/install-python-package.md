<div style="text-align:right"><a href="./index">Examples</a></div>


## Install or upgrade python packages

#### file: hosts.spy

```
hosts = ['host1','host2','host3','host4','host5','host6','host7','host8','host9','host10']
```

#### file: example.spy

```
# you can reuse this settings in many scripts.
$.include('hosts.spy')

# python executable on every host
python3bin = 'python3'
pkgname = 'sshscript'

def installPackage(upgrade=False):
    global python3bin, pkgname
    if upgrade:
        print('upgrading')
        $@{python3bin} -m pip install sshscript --upgrade
    else:
        print('installing')
        $@{python3bin} -m pip install @{pkgname}

    #upgrade pip if necessary
    if 'WARNING: You are using pip version' in $.stderr:
        print('upgrading pip')
        $@{python3bin} -m pip install pip --upgrade

for host in hosts:
    $.connect('john@'+host)
    $@{python3bin} -c "import @{pkgname}"
    if $.exitcode == 0:
        installPackage(upgrade=True)
    else:
        installPackage()
    $.close()
```

#### execution

```
sshscript example.spy --verbose --debug
```
