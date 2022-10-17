<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:

You have many servers, one of them has problem when resolving a FQDN. You want to find the server by ping.

## example.spy

```
hostnameToFind = 'problem.domain.com'
## credentials for loging
username = 'user'
password = '123456'
try:
    ## check a host only, given by CLI
    hosts = [__main__.unknown_args[0][1:]]
except IndexError:
    ## check all hosts
    hosts = ['host1','host2','host3','host4','host5'] # and many others here

for host in hosts:
    print('checking ',host)
    $.connect(f'{username}@{host}',password=password)
    with $ as console:
        ## "0" means not to keey output in memory
        console.sendline(f'ping {hostnameToFind}',0)
        count = 0
        for line in console.lines():
            count += 1
            ## this is important since "ping" runs forever
            if count > 5: break
            ## simply check the IP address on output
            print(line)
        ## explicitly stop the "ping" 
        console.shutdown()
```

## execution
```
## check "host1" only
$sshscript example.spy -host1

## check all hosts
$sshscript example.spy 

```
