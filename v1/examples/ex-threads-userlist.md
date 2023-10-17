<div style="text-align:right"><a href="./index">Examples</a></div>

## Secnario

This example is to collect login-able accounts in 3 groups of hosts. Every group has multiple hosts. In a group, hosts are collected one by one. Every group is run in an individual thread. One more to say is that before starting our data collection , we have to ssh to a bridge host.

![image](https://user-images.githubusercontent.com/4695577/186790699-c7f24979-8f05-4f67-b6f1-9142ba63f3cc.png)

#### file: example.spy

```
import tabulate
import threading

# maybe separate hosts into several groups by their location.
hosts = [
    ['host11','hos12','host13'],
    ['host21','hos22','host23','host24'],
    ['host31','hos32'],
    ]
# suppose that there is a single account to login all of them.
username = 'brucelee'

# connect to bridge host 
$.connect(f'{username}@bridge-host')

$ hostname
print('connected to',$.stdout)

locker = threading.Lock()

# this would be run in every thread
def job(accounts,ret,pkey):
    global job, locker

    # connect to a host in group
    account = accounts.pop(0)
    $.connect(account,pkey=pkey)
    $ hostname
    hostname = $.stdout.strip()

    
    $cat /etc/passwd

    # parse content of /etc/passwd
    regularAccounts = {}
    nonShellKeywords = ('false','nologin','halt','shutdown','sync')
    for line in $.stdout.split('\n'):
        line = line.strip()
        if not line: continue
        elif line.startswith('#'): continue
        cols = line.split(':')
        shells = cols[-1].split('/')
        nonShell = False
        for keyword in nonShellKeywords:
            if keyword in shells:
                nonShell = True
                break
        if not nonShell: regularAccounts[cols[0]] = cols[-1]

    locker.acquire()
    ret[hostname] = regularAccounts
    locker.release()
    
    $.close()
    
    # move to next host in group
    if len(accounts):
        job(accounts,ret,pkey) 

# load the key for doing ssh
pkey = $.pkey(f'/home/{username}/.ssh/id_rsa')

# we would collect data into this bag
ret = {}

# create a thread for every group
threads = []
for i in range(len(hosts)):
    accounts = [(username + '@' + x if x.find('@')==-1 else x ) for x in hosts[i]]
    t = $.thread(target=job,args=(accounts,ret,pkey))
    threads.append(t)
    t.start()

# wait for thread to complete
for i in range(len(threads)):
    threads[i].join()

# output
hostnames = list(ret.keys())
hostnames.sort()
headers = ('usernmae','shell')
for hostname in hostnames:
    usernames = list(ret[hostname].keys())
    usernames.sort()
    rows = []
    for username in usernames:
        rows.append((username,ret[hostname][username]))
    print(hostname)
    print('=' * 40)
    print(tabulate.tabulate(rows,headers=headers))
    print()
```

#### execute the example.spy 
```
$sshscript example.spy
$sshscript example.spy --verbose
$sshscript example.spy --debug
$sshscript example.spy --debug --verbose
```
