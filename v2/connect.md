# SSHScript v2.0 Make Connections

Last Updated on 2023/11/07

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

* [Connect by Password](#bypassword)
* [Connect by SSH Key](#bykey)
* [Connect by ProxyCommand](#byproxycommand)
* [Nested Connection](#nested)

## 🔵 <a name="bypassword"></a>Connect by Password

The common approach to connect is to connect by account and password. For example:
```
## filename: example.spy
## run: sshscript example.spy
with $.connect('user@host','1234') as host_session:
    $hostname
    assert $.stdout.strip() == 'host'
```
Or with sshscript module:
```
## filename: example.py
## run: python3 example.py
import sshscript
session = sshscript.SSHScriptSession()
with session.connect('user@host','1234') as host_session:
    host_session('hostname')
    assert host_session.stdout.strip() == 'host'
```


## 🔵 <a name="bykey"></a>Connect by SSH Key

The recommended approach to connect to remote servers is to use SSH keys, which offer a more secure and convenient alternative to passwords. SSH keys are generated using the ssh-keygen command, which creates a pair of public and private keys. The public key is stored on the remote server, while the private key is kept secret on the client machine.
```
## You can tell Paramiko which key to use
with $.connect('user@host',pkey=$.pkey('/path/to/key')) as host_session:
    $hostname
    assert $.stdout.strip() == 'host'

## Without password and pkey, Paramiko would serch default path for SSH key
## Which usually is "~/.ssh/id_rsa"
with $.connect('user@host') as host_session:
    pass
```

## 🔵 <a name="bykey"></a>Connect by ProxyCommand
Keyword arguments passed to connect(), except for "policy", are passed through to paramiko.SSHClient().connect().
```
with $.connect('user@host',proxyCommand='openssl s_client -ign_eof -connect 1.2.3.4:5555 -quiet') :
    $hostname
    assert $.stdout.strip() == 'host'
```
 
## 🔵 <a name="nested"></a>Nested Connections

Connecting from a bridge host to a protected host is straightforward.
```
with $.connect('user@bridge','1234') as host_session:
    with $.connect('user@database','1234') as inner_host_session:
        inner_host_session('hostname')
        assert inner_host_session.stdout.strip() == 'database'
```

By nesting connections, you can establish deeper levels of connection.

Important note: When making a nested connection, the hostname must be resolvable by the host in the middle. For instance, in the following example:
```
with $.connect('user@bridge','1234') as host_session:
    with $.connect('user@database','1234') as inner_host_session:
        with $.connect('user@accounts','1234') as inner_inner_host_session:
            inner_inner_host_session('hostname')
            assert inner_inner_host_session.stdout.strip() == 'accounts'
```
- The hostname "bridge" is resolvable by localhost.
- The hostname "database" should be resolvable by the "bridge" host.
- The hostname "accounts" should be resolvable by the "database" host.

By default, Paramiko searches for SSH keys on localhost. In the following example, when connecting to the "database" host, Paramiko will use the SSH key on localhost:

```
## using the ssh key on localhost
with $.connect('user@bridge') as host_session:
    ## still using the ssh key on localhost
    with $.connect('user@database') as inner_host_session:
        inner_host_session('hostname')
        assert inner_host_session.stdout.strip() == 'database'
```
To use the SSH key on the "bridge" host, you need to explicitly specify it using the $.pkey() function. For example:

```
with $.connect('user@bridge') as host_session:
    ## "/home/user/.ssh/id_rsa" is on the "bridge" host
    pkey = $.pkey('/home/user/.ssh/id_rsa')
    with $.connect('user@database',pkey=pkey) as inner_host_session:
        inner_host_session('hostname')
        assert inner_host_session.stdout.strip() == 'database'
```

