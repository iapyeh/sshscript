<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario: Create reverse ssh tunnels

Requirement: rforward.py. Please get the rforward.py from [paramiko's repository](https://github.com/paramiko/paramiko/blob/main/demos/forward.py)

## Example 1

![image](https://user-images.githubusercontent.com/4695577/198823526-61607810-fbc5-4952-bcc4-a1579041b8d9.png)


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

## Execution & Tests

```
## Execution on localhost
sshscript example1.spy
```

```
## Tests on host-1
ssh -p 8022 user@localhost
```


## Example 2

![image](https://user-images.githubusercontent.com/4695577/198823568-2f1ab5fd-cfec-4a48-876c-819d8c379d63.png)


```
## filename: example1.spy
from rforward import reverse_forward_tunnel
server_port =  8443
remote_host =  'www.google.com'
remote_port =  443
with $.connect('user@host-1',passwod='123456') as c1:
  with $.connect('user@host-2',passwod='123456') as c2:
     transport = c2.client.get_transport()
     reverse_forward_tunnel(server_port, remote_host, remote_port, transport)
```

## Execution  & Tests
```
## Execution on localhost
sshscript example2.spy
```

```
## Tests on host-2
curl -k -H 'Host: www.google.com' https://127.0.0.1:8443/
```
