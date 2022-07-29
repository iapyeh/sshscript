<div style="text-align:right"><a href="./index">Examples</a></div>

#### file: test.spy
```
# connect host-a by proxyCommand (ssh key already been installed on localhost)
$.connect('user@host-a',proxyCommand='openssl s_client -connect proxy:port')
$hostname

# connect to another host-b with password
password = 'secret'
$.connect('user@host-b',password=password)
with $sudo -S su as console:
    console.expect('password')
    console.sendline(password)
    console.expect('#',timeout=3)
    console.sendline('crontab -l')
    console.sendline('exit')
```

#### execution
```
$sshscript test.spy
```
