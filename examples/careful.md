<div style="text-align:right"><a href="./index">Examples</a></div>

## $.careful()

Since $.careful() works depending on $.exitcode, for local executions, $.careful() works well. But for remote executions, $careful() might only work for one-dollar commands. The "might work" means that it depends on the remote shell and commands' behavior.


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

$.connect('user@host') # ⬅ difference is here.

$.careful(1)
try:
    $ls -l /non/existing
except SSHScriptCareful:
    # this works
    $.exit(1)

try:
    $$ls -l /non/existing
except SSHScriptCareful:
    # Usually this does not work.
    # Since the $.exitcode is usually -1 -1 for remote two-dollars commands.
    # There is not SSHScriptCareful was thrown.
    $.exit(1)

try:
    with $ls -l /non/existing as _:
        pass
except SSHScriptCareful:
    # Usually this does not work.
    # Since the $.exitcode is usually -1 for remote with-dollar commands.
    # There is not SSHScriptCareful was thrown.
    $.exit(1)

```
