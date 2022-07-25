<div style="text-align:right"><a href="./index">Index</a></div>

# Learning SSHScript Chapter 2

Chapter 1 is essential for learning SSHScript, if you did not read it. It is highly recommended to read it before proceeding to this chapter. Frankly speaking, the 90% core of SSHScript has been introduced in Chapter 1, they are the $ (shell command), $.stdout, $.stderr and the $.connect().

Firstly, I would explain why we need the features in this chapter? Let’s modify the hello.spy in the chapter 1 as following lines:

```
# file content of hello.spy
$ echo hello `whoami`
print($.stdout)
```

Suppose that your username is  “john”,  you might expect the output is:

```
hello john
```

But it is not. In fact, it is

```
hello `whoami`
```

The reason is that your expectation requires a shell to work for it. Shell is powerful, it does many tasks without our notice. It is a shell which runs “whoami” to gain “jonh”, then calls the “echo” to print out.Don’t worry, the SSHScript lets you run your code in a shell easily. Just modify the hello.spy like this:

```
# file content of hello.spy
$$ echo hello `whoami`
print($.stdout)
```

The syntax is to just give your commands two $$.

In fact, “|” (pipe), “>” (redirect) and environment variables like $PATH are all dependent on the shell. If your commands utilize them, then just give them a shell by using $$ syntax.

I usually use $$ when calling “sudo”. eg.

```
$$echo my-password | sudo -S ls -l /root
```

## Many commands to run

For $$, you can put many commands line by line behind it as for $. Their difference is that the $$ syntax has an idea of its context. Simply put, it works with a working folder. Please see this example:

```
$.connect('username@host')
$$'''
cd /tmp
ls -l *.txt
rm *.txt
'''
```

The listed content is /tmp and the removed txt files are also in the /tmp. It is because its working folder has changed to the /tmp at line 2 “cd /tmp”.

This behaves differently for $. If the 3 lines are executed by $, the “cd /tmp” makes no sense because they are executed individually. The listed content and files removed are all in your home directly. Which is your default folder when connecting with ssh.

## with

SSHScript also supports interactive shells. The next example would execute “sudo su”, input the required password, then execute 2 commands as root.

```
with $$sudo -S su as console:
    console.sendline('my-password')
    console.sendline('whoami')
    console.sendline('ls -l /root')
```

The “with … as” is regular syntax of Python. With it, you gain a variable (here is “console”) to interact with the shell. You can call sendline(), expect() with the “console”.

The [pexpect](https://pexpect.readthedocs.io/) is excellent for interaction, in respect with it, SSHScript follows its terminology.

For inputting one line, you can call sendline(). It could be giving the password or executing a command. No surprise, you can get the output of execution from console.stdout and console.stderr.

```
with $$sudo -S su as console:
    console.sendline('my-password')
    
    console.sendline('ls -l /root')
    # here, console.stdout has the output of "ls"
    for line in console.stdout.split('\n'):
         print(line.split())

    console.sendline('whoami')
    # now, console.stdout has the output of "whoami"
    assert console.stdout.strip() == 'root'

# Outside the "with closure",
# the $.stdout has all the output of stdout,
$.stdout
# and the $.stdout has all the output of stderr.
$.stderr
```

For the with syntax, you can use $ or $$ after the “with”. They have no difference. For example, the following codes are also valid for SSHScript.

```
#with $$sudo -S su as console:
with $sudo -S su as console:
    console.sendline('my-password')
    console.sendline('whoami')
```
