<div style="text-align:right"><a href="./index">Index</a></div>

# SSHScript使用教學 第一章

SSHScript 是純Python寫的模組，它所能做的事情用Paramiko跟subprocess都做得到。但是SSHScript提供一種比較簡潔、直觀的語法讓你使用Paramiko及subprocess的功能。因為SSHScript可讓程式看起來像是把Shell命令嵌入Python程式中，甚至可以把它看成是一種用Python寫Shell Script的方法。

## 安裝方式

以下兩種方式都可以

```
$pip install sshscript
或者
$python3 -m pip install sshscript
```

或者是

```
$sudo pip install sshscript
或者
$sudo python3 -m pip install sshscript
```

## 升版方式

只要在最後面加上 --upgrade,例如

```
$pip install sshscript --upgrade
```

## 檢查安裝是否成功

一般而言如果pip安裝成功，則在程式內import sshscript不會有問題。但因為SSHScript模組會額外安裝一個可執行檔，名為 sshscript，由於某些緣故可能執行會有問題。本使用教學需依靠sshscript執行檔進行，所以在繼續下去之前，讓我們先檢查sshscript是否安裝成功。檢查sshscript是否可成功執行的方法是在console中，輸入sshscript (小寫）：

```
$ sshscript
```

如果出現類似以下的內容，那就是安裝成功了（版本不一樣，沒關係）

```
SSHScript Version:1.102
usage: sshscript [-h] [--run-order] [--script]...

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

目前已知在某些情況下，setuptools會產生的python執行檔的路徑是錯誤的。當你執行sshscript時會有 bad interpreter的錯誤。輸出可能是這樣：

```
-bash: ... bad interpreter: No such file or directory
```

解決的方法是找到sshscript安裝的路徑：

```
$ which sshscript
```

然後改掉他的第一行。例如第一行可能是這樣：

```
#!/usr/local/bin/python
```

會有"bad interpreter"是因為/usr/local/bin/pytho不存在，可將它改成

```
#!/usr/bin/env python3 
```

或者你那台機器上的python3的路徑。

## SSHScript的使用方式

1. 你編寫含有SSHScript語法的Python程式碼，假設附檔名為.spy，然後執行 “sshscript [你的.spy檔]”。你的程式碼內的SSHScript語法部分替換成可運作的一般Python 語法之後被Python執行。
2. 在你的.py程式中，import sshscript，使用sshscript.runFile() 或 sshscript.runScript()執行含有SSHScript語法的程式碼。

本使用教學的內容說明的是第一種用法。

## Hello World

以下是一個含有SSHScript語法的Python Script。名稱為 hello.spy

```
# 這是hello.spy檔案的內容
$ echo hello world
print($.stdout)
```

執行它

```
# 這是在console 中下指令 "sshscript hello.spy"
$ sshscript hello.spy
# 結果是在console中印出
hello world
```

如果你想知道經過SSHScript轉換之後的”正常”Python Script是什麼，可以這樣做：

```
# 這是在console 中下指令
$ sshscript hello.spy --script
001:try:
002:    __b = """echo hello world """
003:    __c = SSHScriptDollar(None,__b,locals(),globals(),inWith=0)
004:    __ret = __c(0)
005:finally:
006:    _c = __c
007:print(_c.stdout)
008:
```

轉換過的script是什麼不是很容易閱讀，但實際上你並不需要讀懂它。通常只有偶爾在Debug時會想要知道報錯的那行的內容是什麼時會用到 —script的這個參數。

你只需要注意到，你寫了一行的程式碼:

```
$echo hello world
```

這是一行常見的Shell指令。它呼叫 echo 指令，印出 hello world。你把它寫在.spy裡面，SSHScript就會把它轉成subprocess的呼叫，並且把結果放在$.stdout當中讓你在Python中使用:

```
print($.stdout) 
```

上面這一行是典型的Python的程式碼，只是他列印了一個SSHScript才有的特殊變數。接下來讓我們來瞭解這個SSHScript特殊的變數： $.stdout

## $.stdout

請注意有一個小數點在＄後面。

這是一個str變數。內容是最近執行的＄指令從stdout的輸出。例如：

```
$echo hello world
assert $.stdout.strip() == 'hello world'
```

“echo”程式會從stdout輸出”hello word”，因此$.stdout的內容是 “hello world”. 因為它是一個str變數，你可以直接接上 .strip()。你也可以這樣：

```
$ls -l 
for line in $.stdout.split('\n'):
    cols = line.split()
    if len(cols): print('filename=',cols[-1])
```

## $.stderr

既然有$.stdout，也就有$.stderr。請注意有一個小數點在＄後面。

這是一個str變數。內容是最近執行的＄指令從stderr的輸出。例如

```
$ls -l /not-found-folder
print('Error:' + $.stderr) 

執行結果：
Error: ls: /not-found-folder: No such file or directory
```

一般而言，如果執行的指令沒有錯誤，這個變數值是空字串。但有些索取密碼的程序會從stderr輸出密碼提示(password:)，所以$.stderr是什麼內容取決於指令的性質。

## Hello World @Host

上一節的內容中所執行的指令都是在本機localhost上執行的。如果要ssh到遠端主機做相同的事情要怎麼做呢？只要加上一行指令就可以做到。例如：

```
$.connect('yourname@host',password='password')
$ echo hello world
print($.stdout)
```

只要在第一行加上連線到遠端主機的指令$.connect就完成了。

如果你有2台，你可以這麼做：

```
$.connect('yourname@host-a',password='password-a')
$ echo hello world @host-a
print($.stdout)
$.close() # 離開 host-a

$.connect('yourname@host-b',password='password-b')
$ echo hello world @host-b
print($.stdout)
$.close() # 最後這一個$.close()可有可無
```

如果不幸，你實在命苦，host-b躲在host-a之後，你得跳2次才能到達host-b執行工作的主機。沒問題，那就不要關掉host-a的連線，繼續 $.connect 到host-b

```
$.connect('yourname@host-a',password='password-a')
$.connect('yourname@host-b',password='password-b')
$ echo hello world
print($.stdout)
```

只要這4行，你完成了ssh到host-a，再從host-a ssh 到host-b去say hello的任務。

當然，你不只可以say hello, 你還可以做各種你想做的事。

```
$.connect('yourname@host-a',password='password-a')
$.connect('yourname@host-b',password='password-b')

# 察看硬碟容量
$ df
print($.stdout)

#察看網路連線狀況
$ nestat -antu
print($.stdout)

#察看登入情況
$ last -30
print($.stdout)
```

或者做的更多一點

```
$.connect('yourname@host-a',password='password-a')
$.connect('yourname@host-b',password='password-b')

# 假設你有一個送簡訊的Python函式
import sendsms

# 察看硬碟容量
$ df
for line in $.stdout.split('\n'):
    cols = line.strip().split()
    if len(cols) and cols[4][-1] == '%':
          capacity = int(cols[4][:-1])
          if capacity > 80:
              sendsms(f'Warning:{cols[0]} has capacity over 80')
```

說穿了，.spy就是一個.py，Python的函式你想怎麼用就怎麼用。

## ssh with key

如果你不是使用密碼連線，而是用key的話，你可以這樣連線：

```
$.connect('yourname@host-a')
```

通常第一層的ssh這樣就可以成功連線，至少在我的Mac上是這樣。如果不行，或者是第二層的ssh，可以寫的明確一點：

```
keypath = os.path.expanduser('~/.ssh/id_rsa')
# $.pkey() 讀取檔案內的key做ssh登入
$.connect('yourname@host-a',pkey=$.pkey(keypath))
```

第二層(nested ssh)的例子：

```
$.connect('yourname@host-a')
# 請注意， 這是在遠端主機 host-a 上的目錄，不是本機上的目錄
keypath = '/home/yourname/.ssh/id_rsa'
$.connect('yourname@host-b',pkey=$.pkey(keypath))
```

當然，如果你不覺得麻煩的話，你可以把遠端主機上的key file複製到本機，
然後把它從遠端主機上刪除。相對來講，這樣是比較安全。在此情況下，連線可以這樣做：

```
keyA = $.pkey('keys/host-a/id_rsa')
keyB = $.pkey('keys/host-b/id_rsa')
$.connect('yourname@host-a',pkey=keyA)
$.connect('yourname@host-b',pkey=keyB)
```

這是因為$.pkey()有一個特殊的行為：他會根據當下脈絡決定檔案的位置。如果還沒連線，他的路徑是本機檔案，如果已經連線，他的路徑是遠端主機上的檔案。

## Many commands to run

如果你是一個大忙人，有不只一個指令需要執行，你可以把$指令寫成這樣：

```
$'''
df
netstat -antu
last -30
'''
```

在多行字串當中的每一行指令會一個接一個執行（不是同時）。所有的輸出會集合起來放在 $.stdout或$.stderr當中。
