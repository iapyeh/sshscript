<div style="text-align:right"><a href="./index">Index</a></div>

# sshscript執行檔的安裝

## 檢查安裝是否成功

一般而言如果pip安裝成功，在程式內能import sshscript就可以了。但因為SSHScript模組（套件）會額外安裝一個可執行檔，名為 sshscript，由於某些緣故可能無法執行。檢查sshscript是否可執行的方法是在console（命令列）中，輸入sshscript (小寫）：

```
$ sshscript
```

如果出現類似以下的內容，那就是安裝成功了（版本不一樣，沒關係）

```
SSHScript Version:1.102
usage: sshscript [-h] [--run-order] [--script]...(省略）

SSHScript

positional arguments:
  paths               path of .spy files or folders

optional arguments:
  -h, --help          show this help message and exit
  --run-order         show the files to run in order...
  --script            show the converted python scri...
(以下省略）
```

## 如果安裝不成功

### 狀況一：$PATH問題

如果沒有出現上面的畫面的話。先用which找到sshscript安裝的路徑。

```
$ which sshscript
```

如果你用which時就找不到sshscript所在的路徑，那麼可能是sshscript所在的目錄不在$PATH當中。

### 狀況二：Bad Interpreter

如果which找得到sshscript的話。目前已知在某些情況下，setuptools產生的python執行檔的路徑是錯誤的。導致執行sshscript時會有 bad interpreter的錯誤。輸出可能是這樣：

```
-bash: ... bad interpreter: No such file or directory
```

那麼則須編輯sshscript(那是一個文字檔）改掉他的第一行。例如第一行可能是這樣：

```
#!/usr/local/bin/python
```

會有"bad interpreter"是因為/usr/local/bin/python不存在，可將它改成

```
#!/usr/bin/env python3 
```

或者你那台機器上的python3的路徑。

### 其他狀況：

如果不是上述兩種情況，請到本專案[Github上的issue](https://github.com/iapyeh/sshscript/issues)裡留言。
