
## $.careful()

Since $.careful() works depending on $.exitcode, for local execution, $.careful() works well. But for remote execution, $careful() might only work for one-dollar commands. The "might work" means that it depends on the remote shell and commands' behavior.


#### file example-local.spy

```
from sshscript import SSHScriptCareful

$.careful(1)
try:
    $ls -l /non/existing
except SSHScriptCareful:
    # this works
    $.exit(1)

try:
    $$ls -l /non/existing
except SSHScriptCareful:
    # this works
    $.exit(2)

try:
    with $ls -l /non/existing as _:
        pass
except SSHScriptCareful:
    # this works
    $.exit()

```


#### file example-remote.spy

```
from sshscript import SSHScriptCareful

$.connect('user@host') # ⬅ difference is here. (compared with the above example-local.spy)

$.careful(1)
try:
    $ls -l /non/existing
except SSHScriptCareful:
    # this works
    $.exit(1)

try:
    $$ls -l /non/existing
except SSHScriptCareful:
    # usually this does not work
    $.exit(1)

try:
    with $ls -l /non/existing as _:
        pass
except SSHScriptCareful:
    # usually this does not work.
    $.exit(1)

```
