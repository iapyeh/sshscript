<div style="text-align:right"><a href="./index">Examples</a></div>

## Scenario:

A SIP server with a public IP address is always under attack. It might not be a big security problem. But they generate a large amount of logs and are quite noisy, especially when we are relying on log files for debugging. This example demonstrates how to filter out attacking IP addresses of a SIP server by watching the output of tcpdump.


## example.spy

```
import re
badips = set()
patIP = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
with $ as console:
    ## There is a "0" as the second parameter of sendline()
    console.sendline('tcpdump -n port 5060',0)
    for line in console.lines():
        ## attacking sample: 
        ## IP 184.105.190.50.5060 > 193.107.216.98.49651: SIP: SIP/2.0 407 Proxy Authentication Required
        ## in above sample, the bad ip is 193.107.216.98
        if not 'Proxy Authentication Required' in line: continue
        badips.append(patIP.findadd(line)[1])
        ## you have to break this loop explicitly
        ## since "tcpdump" would not stop by itself.
        if len(badips) >= 150: break
    ## kill the running process of "tcpdump"
    console.shutdown()
## output rules for iptables
for badip in badips:
    print(f'-A INPUT -s {badip}/32 -j DROP')
```
## execution
```
$sshscript example.spy 
```
