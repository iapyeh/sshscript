<div style="text-align:right"><a href="./index">Examples</a></div>

#### file: test.spy
```
# connect host-a by proxyCommand (ssh key already been installed on localhost)
$.connect('user@host-a',proxyCommand='openssl s_client -connect proxy:port')
$hostname

#suppose ssh key of host-a already been installed on host-b
with $ssh user@host-b as console:
    console.expect('Last login')
    console.sendline('sudo su')
    console.expect('password')
    console.sendline(password)
    console.expect('#',timeout=3)
    console.sendline('crontab -l')
    console.sendline('exit')
 
```

#### execution examples
```
$sshscript test.spy
$sshscript test.spy --verbose
$sshscript test.spy --verbose --debug
```
