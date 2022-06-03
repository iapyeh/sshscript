# Tutorial

# Scenario I

Suppose that there is a security issue about some version of the openssl. You got to check the version number of the openssl on your all hosts. What you have to do is ssh into each of them and execute command, like this:

**Step 1: in dev-host**

```jsx
$ssh user@host
```

**Step 2:  in ssh console**

```jsx
$openssl version

```

**Step 3: collect the output** 

```jsx
OpenSSL 1.1.1f  31 Mar 2020
```

If you have 5 hosts, you have to repeat step1, step2, step3 for 5 times.

The SSHScript let you do that jobs in this way:

**Step 1: in dev-host, create "check-openssl-version.spy" with content:**

```jsx
# collect
hosts = ['host1','host2','host3','host4','host5']
user = 'your-name'
password = 'your-secret'
opensslVersions = []
for host in hosts:
    with $.open(f'{user}@{host}',password) as _:
	      $openssl version
        opensslVersions.append([host,$.stdout])
# output
from tabulate import tabulate
print(tabulate(opensslVersions, headers=['host','version']))
```

**Step 2: run the “check-openssl-version.spy”  in localhost**

```jsx
$ sshscript check-openssl-version.spy
```

**Step 3: What you get in local console would be something like this:**

```jsx
host     version
-------  --------------------------------
host1    OpenSSL 1.0.2k-fips  26 Jan 2017
host2    OpenSSL 1.1.1k  FIPS 25 Mar 2021
host3    OpenSSL 1.1.1n  15 Mar 2022
host4    OpenSSL 1.1.1o  3 May 2022
host4    OpenSSL 1.0.2g  1 Mar 2016
```

Further more, you can store common settings in a separated file:

Let’s create a new file named “common.spy”

```jsx
#file: common.spy
hosts = ['host1','host2','host3','host4','host5']
user = 'your-name'
password = 'your-secret'
```

And the check-openssl-version.spy can be re-written like this:

```jsx
# collect
**$.include('common.spy')  # <------- look here**
opensslVersions = []
for host in hosts:
    with $.open(f'{username}@{host}',password) as _:
	      $openssl version
        opensslVersions.append([host,$.stdout])
# output
from tabulate import tabulate
print(tabulate(opensslVersions, headers=['host','version']))
```

When your password has changed, and you have about 100 pieces of scripts like the  check-openssl-version.spy . Only the common.spy need to be updated.

# Scenario II

What if you feel unsafe that the common.spy is always there since it contains password of all hosts. You hope that the password could be omitted from the dev-host. Suppose you think that your notebook is safe place to keep the password, then you can do it by this way:

Let’s create a file named “secret.spy” in your notebook.

```jsx
#file: secret
password = ‘your-secret’
```

And modify the common.spy in dev-host to be like this:

```jsx
#file: common.spy
hosts = ['host1','host2','host3','host4','host5']
user = 'your-name'
$.include('secret')
```

Let’s create a file named “run-check-openssl-version.spy” in your notebook

```jsx
# ssh to dev-host
$.open('you@dev-host','password')

# suppose common.spy is in /home/you/project/ on dev-host
$.upload('/home/my/secret','/home/you/project/secret')

# run the check-openssl-version.spy on dev-host
$sshscript check-openssl-version.spy

# remove the secret from dev-host
$rm /home/you/project/secret

```

Then run the run-check-openssl-version.spy on your notebook

```jsx
$sshscript run-check-openssl-version.spy
```
