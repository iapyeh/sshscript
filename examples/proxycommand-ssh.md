# use case
$.connect('user@host',proxyCommand='openssl s_client -connect proxy:port')
$hostname
with $ssh -t user@host as console:
    console.expect('Last login')
    console.sendline('sudo su')
    console.expect('password')
    console.sendline('secret')
    console.expect('#',timeout=3)
    console.sendline('crontab -l')
    console.sendline('exit')
