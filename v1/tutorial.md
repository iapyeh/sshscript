<div style="text-align:right"><a href="./index">Index</a></div>
# Tutorial

# Scenario I

Suppose that there is a security issue about some version of the openssl package. You have to check the version of openssl on all servers. You must ssh into servers from your maintaining host one by one, like this:

```
# Step 1: from the development host ssh to the production host1
$ssh user@host1

# Step 2: on the host1, execute a command to get openssl's version 
# and collect its output
$openssl version
OpenSSL 1.1.1f  31 Mar 2020

# Step 3: repeat the above steps for production host2, host3, ...
```

The SSHScript let you do the jobs in this way:

Step 1: create a file named "check-openssl-version.spy" on the development host

```
# file: check-openssl-version.spy

hosts = ['host1','host2','host3','host4','host5']
user = 'your-name'
password = 'your-secret'
opensslVersions = []
for host in hosts:
    with $.connect(f'{user}@{host}',password=password) as _:
        $openssl version  # ⬅ the shell command to run  
        opensslVersions.append([host,$.stdout])
# output
from tabulate import tabulate
print(tabulate(opensslVersions, headers=['host','version']))
```

Step 2: run the “check-openssl-version.spy”   on the development host

```
$ sshscript check-openssl-version.spy
host     version
-------  --------------------------------
host1    OpenSSL 1.0.2k-fips  26 Jan 2017
host2    OpenSSL 1.1.1k  FIPS 25 Mar 2021
host3    OpenSSL 1.1.1n  15 Mar 2022
host4    OpenSSL 1.1.1o  3 May 2022
host5    OpenSSL 1.0.2g  1 Mar 2016
```

Furthermore, you can store common settings in a separated file:

Let’s create a new file named “common.spy”

```
#file: common.spy
hosts = ['host1','host2','host3','host4','host5']
user = 'your-name'
password = 'your-secret'
```

Then, re-write the check-openssl-version.spy 

```
# file: check-openssl-version.spy

# collect
$.include('common.spy')  # ⬅ look here
opensslVersions = []
for host in hosts:
    with $.connect(f'{username}@{host}',password=password) as _:
        $openssl version
        opensslVersions.append([host,$.stdout])
# output
from tabulate import tabulate
print(tabulate(opensslVersions, headers=['host','version']))
```

When your password has changed, and you have about 100 pieces of scripts like the  check-openssl-version.spy . Only the common.spy needs to be updated.

Furthermore, python code can be put into $command. Which means with little modification, check-openssl-version.spy can check versions of many others. Let’s do it like this:

```
# file: check-openssl-version.spy

# collect
$.include('common.spy')  
opensslVersions = []
appName = 'openssl'  # ⬅ look here
for host in hosts:
    with $.connect(f'{username}@{host}',password=password) as _:
        # ⬇ look below, appName would be replaced by "openssl"
        $@{appName} version    
        opensslVersions.append([host,$.stdout])
            
# output
from tabulate import tabulate
print(tabulate(opensslVersions, headers=['host','version']))
```

Of course, you can run any other commands, like this:

```
# collect
$.include('common.spy')  
for host in hosts:
    # connect to this host
    with $.connect(f'{username}@{host}',password=password) as _:
        # execute the shell command "df"
        $df
        # parse the result in python
        for line in $.stdout.split('\n'):
            cols = line.split()
            partition = cols[0]
            capacity = cols[4][:-1] # drop "%"
            if int(capacity) > 80:
                print(f'Caution:{partition} need help')

```

# Scenario II

Suppose that your development host is in the cloud. Now you think that the common.spy should not be there since it contains passwords of all servers. You hope that those passwords could be kept in your office. And you already have a safe host in your office. Then you can do it by this way:

Let’s create a file named “secret.spy” on the safe host, and put passwords there

```
#file: secret.spy on the safe host (in office)
password = ‘your-secret’
```

Then, modify the common.spy on the development host to be like this:

```
#file: common.spy on the maintaining host in cloud
hosts = ['host1','host2','host3','host4','host5']
user = 'your-name'
$.include('secret.spy')
```

Let’s create a file named “run-from-trusted-host.spy” on the safe host.

```
# file: run-from-safe-host.spy on the safe host (in office)

# ssh to the development host.
$.connect('you@maintaining-host',password='password')

# suppose secret.spy is in /home/my/ on the safe host.
# suppose common.spy is in /home/you/project/ on the development ost.
$.upload('/home/my/secret.spy','/home/you/project/secret.spy')

# run the check-openssl-version.spy on the development host
$sshscript check-openssl-version.spy

# remove the secret from the development host
$rm /home/you/project/secret.spy

```

Then run the run-from-safe-host.spy on the safe host.

```
$sshscript run-from-safe-host.spy
```

Because the secret.spy file is actually a Python script, we can modify it to be like this:

```
#file: secret.spy on the safe host (in office)
from getpass import getpass
password = getpass()
```

By doing so, your password is under your mind only.
