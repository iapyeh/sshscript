<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario: Create a ssh tunnel from a nested ssh connection

Requirement: forward.py. Please get the forward.py from [paramiko's repository](https://raw.githubusercontent.com/paramiko/paramiko/bba5b4ce1ee156e0f5aa685e80c9a172e607ff38/demos/forward.py)

## Example1
![image](https://user-images.githubusercontent.com/4695577/194467519-4201e6fa-00c9-4f23-a734-0e9aef230192.png)

```
from forward import ForwardServer, Handler

## connect to remote host1
c = $.connect('user1@host1',password='123456')
## create the tunnel from localhost:8080 to host2:443 via host1:22
class SubHander(Handler):
    ## hostname or ip of host2
    chain_host = 'host2'
    chain_port = 443
SubHander.ssh_transport = c.client.get_transport()
ForwardServer(('127.0.0.1',8080), SubHander).serve_forever()
## now, you can open https://localhost:8080
## which would be the web server on host2
```


## Example2
If host2:443 is listening on 127.0.0.1 for security reason.
Only host2:22 is available for host1. you can do it by nested ssh as below:
![image](https://user-images.githubusercontent.com/4695577/194467552-5e0d3ecb-66cf-4064-a98b-1fdde387180b.png)


```
from forward import ForwardServer, Handler

## connect to remote host1
$.connect('user1@host1',password='123456')
## connect to remote host2
c = $.connect('user2@host2',password='654321')
## create the tunnel from localhost:8080 to host2:80 directly
class SubHander(Handler):
    chain_host = '127.0.0.1'
    chain_port = 443
SubHander.ssh_transport = c.client.get_transport()
ForwardServer(('127.0.0.1',8080), SubHander).serve_forever()
## now, you can open https://localhost:8080
## which would be the web server on host2
```

## Example 3, is same as the example 1 by "with $.connect" syntax.
```
from forward import ForwardServer, Handler

class SubHander(Handler):
    ## hostname or ip of host2
    chain_host = 'host2'
    chain_port = 443
## connect to remote host1
with $.connect('user1@host1',password='123456') as c:
    ## create the tunnel from localhost:8080 to host2:443 via host1:22
    SubHander.ssh_transport = c.client.get_transport()
    ForwardServer(('127.0.0.1',8080), SubHander).serve_forever()
    ## now, you can open https://localhost:8080
    ## which would be the web server on host2
```
