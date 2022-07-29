<div style="text-align:right"><a href="./index">Examples</a></div>

#### file: test.spy
```
# connect ssh with proxyCommand
$.connect('user@host',proxyCommand='openssl s_client -connect proxy:port')
$hostname

password = 'secret'
$.connect('timwang@rmswks',password=password)
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
