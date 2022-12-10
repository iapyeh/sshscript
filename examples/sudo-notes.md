<div style="text-align:right"><a href="./index">Examples</a></div>

# Some Notes about "sudo"

## sudo requires shell to work

When running commands with sudo, you need to have two-dollars or with-dollar to make it working.

```
# don't work (single dollar)
$echo "password" | sudo -S ls /root

# do work (two-dollars)
$$echo "password" | sudo -S ls /root

# do work (with-dollar)
with $ as console:
    console.sendline('sudo -S whoami')
    console.sendline('password')
    print(f'I am {console.stdout.strip()}')
    ## no need to input password again
    console.sendline('sudo ls -l /root')
    print ($.stdout)
```

## `-p` is our good friend to omit prompt from output

sudo argument "-p" could set the password prompt of sudo. If it is an empty string, there would be no prompt mixed in the output text.

```
## this works but not pretty
$$echo "password" | sudo -S  ls /root

## this is probably better
$$echo "password" | sudo -S -p "" ls /root
```

## `sed` is our good friend to strip ANSI control characters

Some commands produce ANSI control characters when the shell is invoked. 
That's the situation of sudo execution. You can omit those ANSI characters by the "sed". . For example:

```
## this outputs ANSI control characters
$$echo "password" | sudo -p "" -S systemctl list-timers --all

## this would not output ANSI control characters
$$echo "password" | sudo -p "" -S systemctl list-timers --all | sed -e 's/\x1b\[[0-9;]*m//g'
```

[REF: https://superuser.com/questions/380772/removing-ansi-color-codes-from-text-stream](https://superuser.com/questions/380772/removing-ansi-color-codes-from-text-stream)
