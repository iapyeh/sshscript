
## Q: What can it do that Netmiko doesn't do? ([origin](https://www.reddit.com/r/networkautomation/comments/x86lh3/network_automation_in_python/))

Before I was devoting myself to creating SSHScript, I did a little bit of a survey. Netmiko is great. It and SSHScript are based on the same Paramiko. Technically equal. Because I think that the core of so-called automation is to run a lot of os/shell commands. Just I want to have something more likely to embed shell script in python script. That would be more self-explaining for reading and closer to intuition for writing. Especially when maintaining codes among colleagues. That's the reason that SSHScript also integrates the subprocess package. The same code could run on localhost and on remote host. For example:

```
# run a command on localhost by coding in shell-like style
$ ls -l /tmp
```

Then, by adding a line to connect a remote host. We can run the same command on the remote host.

```
$.connect('username@remote-host')
$ ls -l /tmp
```

Then, by adding a line to connect a remote host again. We can run the same command on the nested host behind the remote host.

```
$.connect('username@remote-host')
$.connect('username@remote-nested-host')
$ ls -l /tmp
```
