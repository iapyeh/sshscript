<div style="text-align:right"><a href="./index">Examples</a></div>
## Scenario
This example is to collect login-able accounts in 4 groups of hosts. In a host-group, hosts are collected one by one. Every host-group has multiple hosts. Host-groups are grouped into 2 top-groups.

The main thread would spawn 2 threads for every top-group. Then the thread of a top-group, spawns threads for every host-groups.

Every host group is run in an individual thread. One more to say is that before starting our data collection , we have to ssh to a bridge host.


#### file: example.spy
```
import tabulate
import threading

# define top-groups and host-groups
hostgroups = [
    [
        ['host11','hos12','host13','host14'],
        ['host21','hos22','host23','host24','joe@host25'],
    ],[
        ['host31','hos32','host33','host34'],
        ['host41','bill@hos42','host43'],
    ]]

username = 'jenifer'

# connect to bridge-host
$.connect(f'{username}@bridge-host')

$ hostname
print('connected to',$.stdout)

locker = threading.Lock()
def job(accounts,ret,pkey):
    global job, locker
    account = accounts.pop(0)
    $.connect(account,pkey=pkey)
    
    $cat /etc/passwd
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
    
    if len(accounts):
        job(accounts,ret,pkey)       

# in a top-group, every host group has its own thread
def topgroupjob(hostgroup,ret,pkey):
    groupthreads = []
    
    for hosts in hostgroup:
        accounts = [(username + x if x.find('@')==-1 else x ) for x in hosts]
        t = $.thread(target=job,args=(accounts,ret,pkey))
        groupthreads.append(t)
        t.start()
        
    for t in groupthreads:
        t.join()

pkey = $.pkey(f'/home/{username}/.ssh/id_rsa')
ret = {}
threads = []
# dispatch top group to every thread
for topgroup in hostgroups:
    t = $.thread(target=topgroupjob,args=(topgroup,ret,pkey))
    threads.append(t)
    t.start()

# wait for threads to complete
for t in threads:
    t.join()

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


#### Execution
```
$sshscript blackip.spy
$sshscript blackip.spy --verbose
$sshscript blackip.spy --debug
$sshscript blackip.spy --verbose --debug

```
