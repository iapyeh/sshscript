<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:
Host-a, Host-b are mutully unaccessible for sake of security.
Is there a solution of copying a file from the Host-a to Host-b easily?

## Answer:
Having a bridge Host-c which can access both Host-a and Host-b

![image](https://user-images.githubusercontent.com/4695577/182061077-902d54f0-6a15-4aab-95b3-ebb295a606e8.png)


#### file: example.spy - a file
```
# duplicating a file
srcfile = '/var/log/message'
dstfile = '/data/hosta/var-log-message'
pwd = 'secret'

# make ssh connection to host-a to download file
$.connect(f'user@host-a',password=pwd)
src,dst = $.download(srcfile)
$.close()

# make ssh connection to host-b to upload file
$.connect(f'user@host-b',password=pwd)
$.upload(dst,dstfile)
$.close()

# remove local copy
$rm dst
# or os.unlink(dst)

```

#### file: example.spy - a folder
```
# duplicating a folder
srcfolder = '/var/log'
dstfolder = '/data/hosta'
pwd = 'secret'

# make ssh connection to host-a to download file
$.connect(f'user@host-a',password=pwd)
$tar -zcf /tmp/varlog.tgz @{srcfolder}
src,dst = $.download('/tmp/varlog.tgz')
$.close()

# make ssh connection to host-b to upload file
$.connect(f'user@host-b',password=pwd)
$.upload(dst,'/tmp/varlog.tgz')
$tar -zxf -C @{dstfolder} /tmp/varlog.tgz
# remove temporary file
$rm /tmp/varlog.tgz
$.close()

# remove local copy
$rm dst
# or os.unlink(dst)

```
For more about "tar", please see <a href="https://stackoverflow.com/questions/939982/how-do-i-tar-a-directory-of-files-and-folders-without-including-the-directory-it">here.</a>

#### execute the example.spy on Host-c
```
$sshscript example.spy
$sshscript example.spy --verbose
$sshscript example.spy --debug
```
