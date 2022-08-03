<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:
Generate a list of crackers' ip address by "lastb" command. This list could be used for generating configuation file for "iptable-restore" command to block those ip addresses.

## Answer:

#### file: blackip.spy
```
# generate black list of cracker's ip from "lastb"
"""
output sample of "lastb"
blogdosa ssh:notty    178.128.125.70   Tue Aug  2 09:09 - 09:09  (00:00)
"""

def handleLastbData(stdout):
    # dealing with the output of "lastb"
    cracker = {}
    for line in stdout.split('\n'):
        if not line: continue
        cols = line.split()
        if not len(cols) > 2: continue
        username = cols[0]
        ip = cols[2]
        try:
            cracker[ip].add(username)
        except KeyError:
            cracker[ip] = set([username])

    # do statistics 
    rows = []
    keys = list(cracker.keys())
    keys.sort()
    for ip in keys:
        # add the ip into list if it tried over 5 names
        if len(cracker[ip]) > 5:
            rows.append((ip,len(cracker[ip])))

    # for pretty print
    import tabulate
    print(tabulate.tabulate(rows,headers=('IP','#count')))

    # you can then generate lines like "-A INPUT -s 208.78.41.201/32 -j DROP" 
    # for "iptables-restore" command by the resulting data.
#
# there are 3 methods to run on  localhost
#
if 1:
    # this script is run by root
    $lastb -10000
    handleLastbData($.stdout)
    
elif 0:
    # this script is run by regular user, use sudo to run
    $$echo 123456 | sudo -S lastb -10000
    handleLastbData($.stdout)
    
elif 0:
    # this script is run by regular user, su as root to run
    with $sudo -S su as console:
        console.expect('password')
        console.sendline('123456')
        console.sendline('lastb -10000')
        handleLastbData(console.stdout)
        
#
# there are also 3 methods to run on remote host
#
if 1:
    # login as root
    $.connect('root@host',password='123456')
    $lastb -10000
    handleLastbData($.stdout)
    $.close()

elif 0:
    # login as regular user, then use sudo to run
    $.connect('user@host',password='123456')
    $$echo 123456 | sudo -S lastb -10000
    handleLastbData($.stdout)
    $.close()

elif 0:
    # login as regular user, then su as root to run
    $.connect('user@host',password='123456')
    with $sudo -S su as console:
        console.expect('password')
        console.sendline('123456')
        console.sendline('lastb -10000')
        handleLastbData(console.stdout)
    $.close()
```

#### Examples of execution command
```
$sshscript blackip.spy
$sshscript blackip.spy --verbose
$sudo sshscript blackip.spy
$sudo sshscript blackip.spy --verbose

```
![image](https://user-images.githubusercontent.com/4695577/182344161-e8753829-9be5-4176-8ba4-e660d732c9be.png)
