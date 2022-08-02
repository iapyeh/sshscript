<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:
Generate a list of crackers' ip address by "lastb". This list could be used for generating configuation file for "iptable-restore" to block those ip addresses.

## Answer:

#### file: blackip.spy
```
# generate black list of cracker's ip from "lastb"

"""
output sample of "lastb"
blogdosa ssh:notty    178.128.125.70   Tue Aug  2 09:09 - 09:09  (00:00)
"""
def handleLastbData(stdout):
    # dealing with the output
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
    # for "iptables-restore" by the resulting data.

# this is on localhost
$lastb -10000
handleLastbData($.stdout)


# there are 3 methods to run on remote host

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

#### execute the example.spy on Host-c
```
$sshscript blackip.spy
```
![image](https://user-images.githubusercontent.com/4695577/182344161-e8753829-9be5-4176-8ba4-e660d732c9be.png)

