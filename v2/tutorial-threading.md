# SSHScript 2.0 Tutorial
# SSHScript and Threading (Draft)

Last Updated on 2023/10/20

<div style="text-align:right;position:relative;top:-200px"><a href="./index">Back to Index</a></div>

## Every Thread has an Effective Session.

The "session" here means an instance of SSHScriptSession. Initially, SSHScript creates a session for the main thread.
All commands executed by the initial session are executed by the subprocess module on localhost.
"All commands" includes one-dollar, two-dollars and with-dollar commands.

```
## This command "hostname" would be executed by the subprocess module. 
## Because the effective session is the initial sesssion of the main thread.
$hostname
```

If the initial session was connecting to a remote server. A new instance of SSHScriptSession would be returned by the $.connect() method.
The new instance of SSHScriptSession would become the "effective session" of the main thread.

```
with $.connect('user@remotehost'):
    ## This command "hostname" would be executed by the paramiko module
    ## Because the effective session is the new instance of SSHScriptSession returned by $.connect()
    $hostname
```

SSHScript attaches every dollar-commands to a session to execute it.
For doing that, SSHScript binds a session to every thread, that session is the effective session of the thread.

Every thread carries a stack to hold sessions. Initially, the stack of main thread has one element -- the initial session.
A new connection creates a new session and that session would be put on the stack top to be the effective session.
And it would be pull out of the stack when it was closed.

```
## Initial session would execute the following commands on localhost by subprocess module.
$hostname
$whoami
## The new session would become the effective session of main thread
with $.connect('user@remotehost'):
    ## the effective session which is connected to remotehost would execute the following commands
    $hostname
    $whoami
## Initial session would execute the following commands on localhost by subprocess module.
## Since connection to remotehost is closed.
$hostname
$whoami
```

### When a function comes into play

Let's check the example code below:
```
def get_profile():
    profile = {}
    $hostname
    profile['hostname'] = $.stdout.strip()
    $whoami
    profile['whoami'] = $.stdout.strip()
    return profile

profile = {'localhost':get_profile()}
hosts = ['user@hostA','user@hostB']
for account in hosts:
    with $.connect(account):
        profile[account] = get_profile()
```



## 🔵 <a name="one"></a>

