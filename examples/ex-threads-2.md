<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:
ssh to remote hosts and run commands in parallel by threads.

![image](https://user-images.githubusercontent.com/4695577/183364361-3244b778-4aaa-458e-aed5-d08b2227d49d.png)

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

def job(account,pkey,ret):
    # this example shows how to load private key for authentication
    $.connect(account,pkey=pkey)

    # executing command
    $ hostname
    ret['hostname'] = $.stdout
    
    # executing command
    $ date
    ret['date'] = $.stdout
    
    $.close()

pkey = $.pkey('/home/user/.ssh/id_rsa')

# invoking thread-1
ret1 = {}
t1 = $.thread(target=job,args=('user@host-b', pkey, ret1))

# invoking thread-2
ret2 = {}
t2 = $.thread(target=job,args=('user@host-c',pkey, ret2))

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
