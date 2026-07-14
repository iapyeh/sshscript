<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario: Create a ssh tunnel from an existing ssh connection

Requirement: forward.py. Please get the forward.py from [paramiko's repository](https://github.com/paramiko/paramiko/blob/main/demos/forward.py)

## Example 1
![image](https://user-images.githubusercontent.com/4695577/194468408-ea090155-609d-493b-a918-eac64be19b18.png)

```
from forward import forward_tunnel
## connect to remote host1
c = $.connect('user1@host1',password='123456')
## create the tunnel from localhost:8080 to host2:443 via host1:22
forward_tunnel(8080,'host2',443,c.client.get_transport())
```

The above example listens on all IP addresses of localhost.
If you'd like it to listen on 127.0.0.1 only, you can use the following code:

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

## Example 2
For security reason, if host2:443 is listening on 127.0.0.1, or only host2:22 is available for host1. you can do it by nested ssh as below:
![image](https://user-images.githubusercontent.com/4695577/194468445-1c991179-c09c-4bd7-9c30-5800dcca5835.png)

```
from forward import forward_tunnel
## connect to remote host1
$.connect('user1@host1',password='123456')
## connect to remote host2
c = $.connect('user2@host2',password='654321')
## create the tunnel from localhost:8080 to host2:443 via both host1:22 and host2:22
forward_tunnel(8080,'host2',443,c.client.get_transport())
```

The above example listens on all IP addresses of localhost.
If you'd like it to listen on 127.0.0.1 only, you can use the following code:


```
from forward import ForwardServer, Handler

## connect to remote host1
$.connect('user1@host1',password='123456')
## connect to remote host2
c = $.connect('user2@host2',password='654321')
## create the tunnel from localhost:8080 to host2:443 via both host1:22 and host2:22
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
