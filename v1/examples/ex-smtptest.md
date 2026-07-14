<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:
If you want to know if a smtp server would accept mail from your host.
You can use sshscript to create a script to send a mail by connecting to the smtp server using the SMTP protocol.


#### file: mailtest.spy
```
import re, datetime
host = 'smtp.your.domain'
port = 25
mailfrom = 'you@your.domain'
mailto = 'she@her.domain'
subject = f'test at {datetime.datetime.now()}'

## uncomment the next line if you want to test on remote host.
#$.connect('username@remote_host')

## This script requires "telnet" to run. 
## You can use an equivalent like "nc -v" by modifying the next line.
with $telnet @{host} @{port} as console:
    console.expect(re.compile('.+')) # any response
    console.sendline(f'helo')
    console.sendline(f'mail from: {mailfrom}')
    console.sendline(r'rcpt to: {mailto}')
    console.sendline('data')
    ## wait longer, in care the smtp server responses slowly
    console.expect('CRLF',180)
    body = f'''subject: {subject}
from: {mailfrom}

have a nice day.
.
'''
    
    if 1:
        ## for v1.1.17 or lower
        console.sendline([body])
    else:
        ## for v.1.1.18 and above
        console.sendline(body,raw=1)  
    
    console.expect(re.compile('.+'))
    console.sendline('quit')
```

#### Examples of execution command
```
$sshscript mailtest.spy
$sshscript mailtest.spy --verbose
$sshscript mailtest.spy --verbose --debug

```

