<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:
ssh to remote hosts and run commands in parallel by threads more complex example.

![image](https://user-images.githubusercontent.com/4695577/183380792-86ceae61-3b8e-422f-bb76-834ea55cc893.png)

Note: this example require sshscript version >= 1.1.12

#### file: example.spy 
```
# If the localhost can connect host-b, host-c directly, 
# We don't need to connect bridge host, just comment-out the next line.
$.connect('user@host-a')

$ hostname
print('connected to',$.stdout)

def job(accounts,ret,pkey):
    # this is required
    global job
    
    account = accounts.pop(0)
    $.connect(account,pkey=pkey)
    $ hostname
    print('connected to',$.stdout)    
    hostname = $.stdout.strip()
    # knowing which ip makes the connection
    # and ensures that "exeution in shell" works
    $$'''
    echo $SSH_CLIENT
    cd /tmp
    pwd
    '''
    # ensures that "single command execution" works    
    twoDollarsResult = $.stdout
    $ date

    # collect data
    oneDollarsResult = $.stdout
    ret[hostname] = '\n'.join([f'@{oneDollarsResult}',twoDollarsResult])

    # recursively ssh to next hosts
    if len(accounts):
        # load ssh key again from current connected host
        pkey = $.pkey('/home/user/.ssh/id_rsa')
        job(accounts,ret,pkey)
    else:
        $.close()

pkey = $.pkey('/home/user/.ssh/id_rsa')

# ssh to host-b1 to do the task, then ssh to host-b2 from host-b1 to do the task
accounts1  = ['user@host-b1','user@host-b2']
ret1 = {}
t1 = $.thread(target=job,args=(accounts1,ret1,pkey))

# ssh to host-c1 to do the task, then ssh to host-c2 from host-c1 to do the task
accounts2  = ['user@host-c1','user@host-c2']
ret2 = {}
t2 = $.thread(target=job,args=(accounts2,ret2,pkey))

t1.start()
t2.start()
t1.join()
t2.join()

from pprint import PrettyPrinter
pp = PrettyPrinter(indent=4)
pp.pprint(ret1)
pp.pprint(ret2)
```

#### execute the example.spy 
```
$sshscript example.spy
$sshscript example.spy --verbose
$sshscript example.spy --debug
$sshscript example.spy --debug --verbose
```
