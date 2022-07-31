<div style="text-align:right"><a href="./index">Examples</a></div>

## SSHScript and "pytermgui"

"pytermgui" is an excellent Python TUI framework. This example shows that it can get data from the remote console easily by sshscript.

pytermgui: https://github.com/bczsalba/pytermgui

#### file: demopytermgui.spy
```
import pytermgui as ptg

# comment-out the next line to get free memory of localhost
$.connect('user@host-a')

def macro_freememory(fmt: str) -> str:
    # We do not need to call $hostname every time.
    # It is here just for proving that it is actually executing on remote host.
    $ hostname
    hostname = $.stdout.strip()
    
    # collect data of free memory by "vmstat"
    $ vmstat 1 1
    amount = $.stdout.split("\n")[2].split()[3]
    return f'host "{hostname}" has free memory {amount}'

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

####Screenshot of execution:
![image](https://user-images.githubusercontent.com/4695577/182014011-2006db55-8ba1-4a49-9de9-a52a7901de6c.png)

