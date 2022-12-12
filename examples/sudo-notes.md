<div style="text-align:right"><a href="./index">Examples</a></div>

# Some Notes about "sudo"

## with one-dollar command (remote only)

Examples of running sudo commands with one-dollar

```
# single dollar, works on remote (paramiko), not works on localhost(subprocess)
$.connect('user@host')
$sudo -p "" -S <<< "password" ls /root
```
This format "<<<" works on localhost only, if you want to use it, you have to use two-dollars on localhost.

## sudo works with shell (two-dollars and with-dollars)

Examples of running sudo commands with two-dollars or with-dollar:

```
# two-dollars 
$$sudo -p "" -S <<< "password" ls /root

# two-dollars
$$echo "password" | sudo -p "" -S ls /root

# with-dollar
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
## command => sed -e 's/\x1b\[[0-9;]*m//g'
$$echo "passwd" | sudo -S systemctl list-timers| sed -e 's/\\x1b\\[[0-9;]*m//g'
```

[REF: https://superuser.com/questions/380772/removing-ansi-color-codes-from-text-stream](https://superuser.com/questions/380772/removing-ansi-color-codes-from-text-stream)
