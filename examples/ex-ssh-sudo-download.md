<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:

Ssh to a remote host, su as root and download root's files

![image](https://user-images.githubusercontent.com/4695577/182082615-558d146c-de5f-4efb-b732-c1279262ffb6.png)


## Solution:

#### file: example.spy
```
file = '/root/file.tgz'
tmpfile = '/tmp/file.tgz'
pwd = 'secret'
user = 'user'
host = 'host'
# make ssh connection
$.connect(f'{user}@{host}',password=pwd)
# sudo as root to modify file's mode
with $sudo -S su as console:
    console.expect('password')
    console.sendline(pwd)
    # copy as a temporary file
    console.sendline(f'cp {file} {tmpfile}')
    # set owner of the temporary file to "user"
    console.sendline(f'chown {user} {tmpfile}')

# download the temporary file with "user"
src, dst = $.download(tmpfile)
print('downloaded as ', dst)

# remove the temporary file
$rm @{tmpfile}

# close the connnection
$.close()

# ls folder on localhost
$ls -l 

```

#### execution examples
```
$sshscript example.spy
$sshscript example.spy --verbose
$sshscript example.spy --debug
```


Origin: https://www.facebook.com/groups/gpython/posts/10157054268769579/
