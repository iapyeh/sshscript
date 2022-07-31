<div style="text-align:right"><a href="./index">Examples</a></div>

## SSHScript and "pytermgui"

pytermgui: https://github.com/bczsalba/pytermgui

#### file: demopytermgui.spy
```
import pytermgui as ptg

def macro_freememory(fmt: str) -> str:
    # get the data from shell command "vmstat"
    $vmstat 1 1
    amount = $.stdout.split("\n")[2].split()[3]
    return f'{amount}'

ptg.tim.define("!freememory", macro_freememory)

with ptg.WindowManager() as manager:
    manager.layout.add_slot("Body")
    manager.add(
        ptg.Window("[bold]The free memory is:[/]\n\n[!freememory 75]%c", box="EMPTY")
    )

```

#### execution examples
```
$sshscript demopytermgui.spy
$sshscript demopytermgui.spy --verbose
$sshscript demopytermgui.spy --debug
```
