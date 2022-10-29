<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario: Create a ssh tunnel from an existing ssh connection

Requirement: forward.py. Please get the forward.py from [paramiko's repository](https://github.com/paramiko/paramiko/blob/main/demos/forward.py)

## Example 1

![image](https://user-images.githubusercontent.com/4695577/198820453-23c3f2d7-4131-4f14-a5ec-94555cd3858e.png)


```
## filename: example1.spy
from rforward import reverse_forward_tunnel
server_port =  8022
remote_host =  'host-2'
remote_port =  22
with $.connect('user@host-1',passwod='123456') as c:
  transport = c.client.get_transport()
  reverse_forward_tunnel(server_port, remote_host, remote_port, transport)
```

## Execution
```
sshscript example1.spy
```


## Example 2
![image](https://user-images.githubusercontent.com/4695577/198820535-6c809f7e-0490-4de1-89c7-fed36943707b.png)

```
## filename: example1.spy
from rforward import reverse_forward_tunnel
server_port =  8443
remote_host =  'host-2'
remote_port =  443
with $.connect('user@host-1',passwod='123456') as c:
  transport = c.client.get_transport()
  reverse_forward_tunnel(server_port, remote_host, remote_port, transport)
```

## Execution
```
sshscript example2.spy
```
