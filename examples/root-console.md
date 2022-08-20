
<div style="text-align:right"><a href="./index">Examples</a></div>

## Ways to get a root's console on localhost (subprocess)
```
password = '1234'

# method 1
with $ as shell:
    shell.sendline('sudo -S /bin/bash')
    shell.expect('password')
    shell.sendline(f'''{password}
    whoami
    echo shell is $0
    ''')

# method 2
with $#!/bin/bash as shell:
    shell.sendline('sudo -S su')
    shell.expect('password')
    shell.sendline(f'''{password}
    whoami
    echo shell is $0
    ''')


# method 3
with $sudo -S /bin/sh as shell:
    shell.expect('password')
    shell.sendline(f'''{password}
    whoami
    echo shell is $0
    ''')

```

## Ways to get a root's console on remote host (ssh-Paramiko)

```
$.connect('user@host')

password = '1234'
# method 1
with $ as shell:
    shell.sendline('sudo /bin/bash')
    shell.expect('password')
    shell.sendline(f'''{password}
    whoami
    echo shell is $0
    ''')

# method 2
with $#!/bin/bash as shell:
    shell.sendline('sudo -S su')
    shell.expect('password')
    shell.sendline(f'''{password}
    whoami
    echo shell is $0
    ''')

# method 3
with $sudo /bin/sh as shell:
    shell.expect('password')
    shell.sendline(f'''{password}
    whoami
    echo shell is $0
    ''')
 ```
 
## Note
 
"Method 2" is valid in both local and remote scenario:
```
# method 2
with $#!/bin/bash as shell:
    shell.sendline('sudo -S su')
    shell.expect('password')
    shell.sendline(f'''{password}
    whoami
    echo shell is $0
    ''')
```
