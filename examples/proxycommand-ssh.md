```
# connect ssh with proxyCommand
$.connect('user@host',proxyCommand='openssl s_client -connect proxy:port')
$hostname

# ssh to another host and sudo to root
with $ssh user@host2 as console:
    console.expect('Last login')
    console.sendline('sudo su')
    console.expect('password')
    console.sendline('secret')
    console.expect('#',timeout=3)
    console.sendline('crontab -l')
    console.sendline('exit')
```
