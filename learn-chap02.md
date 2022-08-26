<div style="text-align:right"><a href="./index">Index</a></div>

# Learning SSHScript Chapter 2

Chapter 1 is essential for learning SSHScript, if you did not read it. It is highly recommended to read it before proceeding to this chapter. Frankly speaking, the core features of SSHScript have been introduced in Chapter 1, they are the $ (shell command), $.stdout, $.stderr and the $.connect().

## Two-dollars command ($$)

At beginning, let us see why we need the features in this chapter? Let’s modify the hello.spy in Chapter 1 by adding `whoami` after "hello".

```
# file content of hello.spy
$ echo hello `whoami`
print($.stdout)
```

Suppose that your username is  “john”,  you might expect its output is:

```
hello john
```

But it is not. It is:

```
hello `whoami`
```

The reason is that your expectation requires a shell to work for it. Shell is powerful, it does many tasks without our notice. It is a shell which runs “whoami” to gain “jonh”, then calls the “echo” to print them out. Don’t worry, the SSHScript lets you run your code in a shell easily. Just modify the hello.spy like this:

```
# file content of hello.spy
$$ echo hello `whoami`
print($.stdout)
```

The receipt is to give your commands two dollars ($$).

In fact, “\|” (pipe), “\>” (redirect) and environment variables like $PATH are all dependent on the shell. If your commands utilize them, then just give them a shell by using two $$.

An example is that when calling “sudo”, you need two dollars($$).

```
$$echo my-password | sudo -S ls -l /root
```

## Multi-lines two-dollars command

For two dollars ($$), you can put multiple commands line by line behind it as same as one dollar ($). Their difference is that the $$ has an idea of its context because its process is a shell. Simply put, it works with a working folder. Please see this example:

```
$.connect('username@host')
$$'''
cd /tmp
ls -l *.txt
rm *.txt
'''
```

The listed content is /tmp and the removed txt files are also in the /tmp. It is because its working folder has changed to the /tmp at line 2 “cd /tmp”.

This behavior is different for the one dollar $. For one dollar $,  the 3 lines are executed separately, the second command “cd /tmp” makes no sense. The listed content and files being removed are all in your login directory (home directory).

## With-command

The SSHScript also supports interactive shells. The keyword is “with”. The next example demonstrates execution of “sudo su”, inputting the required password, then executing 2 commands as root.

```
with $$sudo -S su as console:
    console.sendline('my-password')
    console.sendline('''
             whoami
             ls -l /root
             ''')
```

The “with … as” is regular syntax of Python. With it, you gain a variable (here is “console”) to interact with the shell. You can call sendline(), expect() with the “console”.

with respect to the pexpect module is the most excellent for interaction with processes, the SSHScript follows its terminology to provide interaction functions.

For inputting one line, you can call sendline(). It might be giving a password or executing a command. As usual, you can get the output of execution from console.stdout and console.stderr.

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

For the with syntax, you can use one dollar $ or two dollars $$ after the “with”. They are the same. For example, the following codes are also valid.

```
#with $$sudo -S su as console:
with $sudo -S su as console:
    console.sendline('my-password')
    console.sendline('whoami')
```
