<div style="text-align:right"><a href="./index">Index</a></div>

# Release Notes of v1.1.17

## New feature: Streaming-style Execution Support

Some commands, like “tcpdump”, would generate data like a stream. They would run forever until being interrupted. SSHScript now supports this kind of execution on localhost and remote hosts. For example:

```
import re
badips = set()
patIP = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
with $ as console:
    console.sendline('tcpdump -n port 5060',0)
    for line in console.lines():
        if not 'Proxy Authentication Required' in line: continue
        badips.append(patIP.findadd(line)[1])
        if len(badips) >= 15: break
    console.shutdown()
for badip in badips:
    print(f'-A INPUT -s {badip}/32 -j DROP')

```

Below are the same codes with comments for better understanding.

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
        ## otherwise this could become an infinite loop.
        if len(badips) >= 15: break
    ## kill the running process of "tcpdump"
    console.shutdown()
## output rules for iptables
for badip in badips:
    print(f'-A INPUT -s {badip}/32 -j DROP')
```

## Refine: console.sendline(command, timeout=None, dataType=3)

The console.sendline() of with-command  has a third parameter “dataType”. It controls the value of console.stdout, console.stderr, $.stdout and $.stderr. 

When dataType is 1, outputs on stdout are collected only. You can get them from console.stdout and $.stdout. But console.stderr and $.stderr have no data.

When dataType is 2, outputs on stderr are collected only. You can get them from console.stderr and $.stderr. But console.stdout and $.stdout have no data.

When dataType is 3, both outputs on stdout and stderr are collected. This is the default behavior. 

The main reason for the third parameter “dataType” is below:

When dataType is 0, none of the outputs on stdout and stderr are collected. This is for commands like `tcpdump` which generates tons of data. To keep that data in memory is not necessary.

For your convenience, when timeout is zero, the dataType would be automatically set to 0 too. 

```
with $ as console:
    ## the following two statements are the same:
    console.sendline('tcpdump -n port 5060',0)
    console.sendline('tcpdump -n port 5060',0,0)
    ## the next statement (for loop) might not be executed 
    ## if timeout of sendline() is great than 0.
    for line in console.lines():
        ...
```

Please note that in the above example, setting timeout to 0 is important. Which tells SSHScript to move to the next statement on execution. If timeout is not zero, SSHScript would start to receive data on stdout and stderr till an interval (timeout seconds) without any data being received. Some commands like the tcpdump generate so many outputs, there might be no such interval. The result is that next lines (such as “for line in console.lines()”) have not been executed.

The default value of timeout is os.environ.get(’CMD_INTERVAL’, 0.5) or os.environ.get(’SSH_CMD_INTERVAL’, 0.5) . 

## New feature: console.lines(timeout=None, dataType=1)

### timeout

When executing a long running command (eg. tcpdump). You can get its output by iterating console.lines(). 

The “timeout” parameter is a break condition to end the looping. When the interval length of no data received has exceeded timeout seconds, a TimeoutError would be raised. The default value is os.environ.get(’CMD_TIMEOUT’,60). When the timeout is 0, this is an infinite loop.

```

with $ as console:
    console.sendline('tcpdump -n port 5060',0)
    try:
	for line in console.lines(10):
            pass
    except TimeoutError:
        ## no data received over 10 seconds
        pass
console.shutdown()

```

### dataType

The “dataType” parameter controls the source of data being iterated.

When dataType is 1, looping on the command's stdout data.

When dataType is 2, looping on the command’s stderr data.

When dataType is 3, looping on both. A tuple is returned. For example:

```

with $ as console:
    console.sendline('tcpdump -n port 5060',0)
    try:
	for (t,line) in console.lines(10,dataType=3):
            if t == 1: print('stdout:',line) # line is from stdout
            if t == 2: print('stderr:',line) # line is from stderr
    except TimeoutError:
        ## no data received over 10 seconds (neither stdout nor stderr)
        pass
console.shutdown()
```

## Refine: console.shutdown()

This call would interrupt the running command. For local executions, it calls subprocess.Popen’s kill(). For remote executions, it calls Paramiko Channel’s shutdown(2) and close().

console.kill() is a alias of console.shutdown()

## Refine: console.send_signal(signal)

This call would send a signal to the running command. This is only valid for local execution.

## Refine: \-\-version

The auto-version-checking feature of v1.1.15 has been revoked. Starting from v1.1.17, you can use \-\-version to display SSHScript’s version. It would also check if your installation is the most updated version.

## Refine: value = $.careful()

Starting from v1.1.17, $.careful() would return the current value. This could be used to restore to original value after changing it.

## Refine: auto “exit” from shell for remote executions

Remote execution of two-dollars and with-dollar commands would invoke shell. After execution that shell is killed by signal 1. So their \$.exitcode is -1. Starting from v1.1.17, an “exit” command was sent automatically to logout from that shell. So, their \$.exitcode would be 0.
