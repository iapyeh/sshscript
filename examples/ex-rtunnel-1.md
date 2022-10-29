<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario: Create a ssh tunnel from an existing ssh connection

Requirement: rforward.py. Please get the rforward.py from [paramiko's repository](https://github.com/paramiko/paramiko/blob/main/demos/forward.py)

## Example 1

![image](https://user-images.githubusercontent.com/4695577/198821100-eb565541-bd6e-4f0d-90ca-9002c55f561f.png)


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

![image](https://user-images.githubusercontent.com/4695577/198821107-631365d8-3658-4604-be07-a11c7e3f5fa4.png)

```
## filename: example1.spy
from rforward import reverse_forward_tunnel
server_port =  8443
remote_host =  'host-3'
remote_port =  443
with $.connect('user@host-1',passwod='123456') as c1:
  with $.connect('user@host-2',passwod='123456') as c2:
     transport = c2.client.get_transport()
     reverse_forward_tunnel(server_port, remote_host, remote_port, transport)
```

## Execution
```
sshscript example2.spy
```
