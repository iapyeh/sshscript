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
    # copy as a temporary file
    console.sendline(f'cp {file} /tmp/file.tgz')
    # set owner of the temporary file to "user"
    console.sendline(f'chown {user} /tmp/file.tgz')

# download the temporary file with "user"
src,dst = $.download('/tmp/file.tgz')
print('downloaded as ',dst)

# remove the temporary file
$rm /tmp/file.tgz
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
