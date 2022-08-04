<div style="text-align:right"><a href="./index">Examples</a></div>

This example requires SSHScript v1.1.9 or above to work. You can upgrade the SSHScript by "pip install sshscript --upgrade".

## py_cui and threading

<a target="_blank" href="https://github.com/jwlodek/py_cui">py_cui</a> is an excellent Python TUI framework.
This example shows that SSHScript can works with threading. 

#### file: demopy_cui_threaing.spy
```
import py_cui
import os, logging
import time,random
import math
global PyCUI,Runner
PyCUI = py_cui.PyCUI
class Runner(object):
    def __init__(self,name,account,textbox):
        self.account = account
        self.textbox = textbox
        self.textbox.set_title(name)
        self.stop = False
        t = $.thread(target=self.run)
        t.start()
    
    def run(self):
        try:
            $.connect(self.account)
            $hostname
            hostname = $.stdout.strip()
            while not self.stop:
                $date
                line = f'{hostname}:{$.stdout.strip()}'
                self.textbox.set_text(line)
                time.sleep(2)
            $.close()
        except Exception as e:
            self.textbox.set_title(self.account)
            self.textbox.set_text('Error')
            print(e)
class Sample:
    def __init__(self, master: PyCUI,accounts,size):
        global math
        self.master = master
        self.runners = []     
        rowcount,colcount = size
        for i,account in enumerate(accounts):
            row = math.floor(i / colcount)
            col = i % colcount
            textbox = self.master.add_text_box('',row,col,initial_text=f'')
            self.runners.append(Runner(f'host#{i+1}',account,textbox))
    def stop(self):
        for r in self.runners:
            r.stop = True

# You have to modify the following 2 lines 
hosts = ('host1','host2','host3','host4','host5')
username = 'username'

accounts = []
for host in hosts:
    accounts.append(username + '@' + host)

colcount = 2
rowcount = math.ceil(len(hosts)/float(colcount))
root = py_cui.PyCUI(rowcount,colcount)
root.set_title('Date on Hosts')
root.set_refresh_timeout(1)
root.enable_logging(logging_level=logging.ERROR)
s = Sample(root,accounts,(rowcount,colcount))
root.start()
s.stop()

```

#### execution examples
```
$sshscript demopy_cui_threaing.spy
```

#### Screenshot of execution:
![image](https://user-images.githubusercontent.com/4695577/182831441-5405758c-4e83-4c04-8409-aa54abeccf72.png)

