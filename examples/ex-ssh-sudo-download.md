<div style="text-align:right"><a href="./index">Examples</a></div>

## Question:
How to ssh to a remote host, su as root and download root's files

## Answer:

#### file: example.spy
```
file = '/root/file.tgz'
pwd = 'secret'
user = 'user'
host = 'host'
# make ssh connection
$.connect(f'{user}@{host}',password=pwd)
# sudo as root to modify file's mode
with $sudo -S su as console:
    console.expect('password')
    console.sendline(pwd)
    console.sendline(f'ls -l {file}')
    console.sendline(f'chmod a+r {file}')

# download the file with "user"
src,dst = $.download(file)
print('downloaded as ',dst)

# sudo as root to restore file's mode
with $sudo -S su as console:
    console.expect('password')
    console.sendline(pwd)
    console.sendline(f'chmod a-r {file}')
    console.sendline(f'ls -l {file}')
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
