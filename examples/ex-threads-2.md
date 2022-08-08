<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:
ssh to many hosts to run commands by threads.


Note: this example require sshscript version >= 1.1.12

#### file: example.spy 
```
# If the localhost can connect host-b, host-c directly, 
# We don't need to connect bridge host, just comment-out the next line.
$.connect('user@host-a')

$ hostname
print('connected to',$.stdout)

# if you are interested of its outupt
# os.environ['VERBOSE'] = '1'

def job(account,ret):
    # this example shows how to load private key for authentication
    pkey = $.pkey('/home/user/.ssh/id_rsa')
    $.connect(account,pkey=pkey)

    # executing command
    $ hostname
    ret['hostname'] = $.stdout
    
    # executing command
    $ date
    ret['date'] = $.stdout
    
    $.close()

# invoking thread-1
ret1 = {}
t1 = $.thread(target=job,args=('user@host-b',ret1))

# invoking thread-2
ret2 = {}
t2 = $.thread(target=job,args=('user@host-c',ret2))

t1.start()
t2.start()

t1.join()
t2.join()

print(ret1)
print(ret2)

```

#### execute the example.spy 
```
$sshscript example.spy
$sshscript example.spy --verbose
$sshscript example.spy --debug
$sshscript example.spy --debug --verbose
```
