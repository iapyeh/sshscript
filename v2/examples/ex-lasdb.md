<div style="text-align:right"><a href="./index">Back to Index</a></div>

## Who is attacking your server?
The lastb command in Linux displays a list of failed login attempts by users. It retrieves the information from the /var/log/btmp file, which records unsuccessful login attempts. We can use lastb to generate a list of crackers' IP addresses, and then generate a configuration file for iptables to block them.

```
def getBadIPAddresses(stdout):
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
    badIPAddresses = []
    keys = list(cracker.keys())
    keys.sort()
    for ip in keys:
        ## add the ip into list if it tried over 5 names
        if len(cracker[ip]) > 5:
            badIPAddresses.append(ip)
    return badIPAddresses   
    
password = '123456'
$.connect('user@host',password):
    with $.sudo(password) as sudo:
        sudo('lastb -1000')
        badIPAddresses = getBadIPAddresses(sudo.stdout)
        ## rules for iptables
        rules = []
        for ip in badIPAddresses:
            rules.append(f'-A INPUT -s {ip}/32 -j DROP')
        print('\n'.join(rules))    
```

