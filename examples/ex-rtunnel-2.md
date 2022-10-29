<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario: Create socks5 proxy over ssh

This would enable a heavily protected host to access internet for updating packages, executing ["pip install"](https://stackoverflow.com/questions/22915705/how-to-use-pip-with-socks-proxy) or something like that.

### Dependence:

- [socksproxy.py](https://github.com/iapyeh/sshscript/blob/gh-pages/examples/socksproxy.py)

## Example 1

![image](https://user-images.githubusercontent.com/4695577/198825127-a3417cf8-704d-4946-b851-07ea67ed356e.png)

```
## filename: example1.spy
from socksproxy import ThreadingSocksProxy
import threading, traceback
remote_port = 8080

with $.connect('user@host-1',password='123456') as c1:
    with $.connect('user2@host-2',password='123456') as c2:
        try:
            transport = c2.client.get_transport()
            ThreadingSocksProxy(transport,remote_port).start().join()
            ## To require credentials for client, do it like blow:
            #ThreadingSocksProxy(transport,remote_port,'username','password').start().join()
        except KeyboardInterrupt:
            pass
        except:
            traceback.print_exc()
          

```

## Execution & Tests

```
## Execution on localhost
sshscript example1.spy
```

```
## Tests on host-2
curl -k -x socks5h://localhost:8080 https://www.google.com
## When requires credentials
curl -k -U username:password -x socks5h://localhost:8080 https://www.google.com
```
