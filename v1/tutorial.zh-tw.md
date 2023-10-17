<div style="text-align:right"><a href="./index">Index</a></div>

# 導覽

# 應用情境一

假設有天爆發一個消息：某個版本的openssh有資安風險，你必須立刻檢查好幾台伺服器上openssh的版本。你得從維運機（跳板機）上ssh到每一台主機查詢openssh的版本時，你的步驟大概是這樣：

```
# Step 1: 從維運機ssh到主機#1
$ssh user@host1

# Step 2: 在主機#1上,執行指令，把輸出的版本抄下來
$openssl version
OpenSSL 1.1.1f  31 Mar 2020

# Step 3: 重複上述步驟將所有抄下來的資料彙整成報表
```

SSHScript 可以讓你把上述的工作改成這樣：

Step 1: 在維運機上建立一個檔案名為 "check-openssl-version.spy" 

```jsx
# file: check-openssl-version.spy 內容
# 假設有5台機器
hosts = ['host1','host2','host3','host4','host5']
# 登入帳號
user = 'your-name'
# 登入密碼
password = 'your-secret'
opensslVersions = []
for host in hosts:
    # ssh 到主機上執行指令，並蒐集輸出
    with $.connect(f'{user}@{host}',password=password) as _:
        $openssl version  # ⬅ the shell command to run  
        opensslVersions.append([host,$.stdout])
# 輸出報表
from tabulate import tabulate
print(tabulate(opensslVersions, headers=['host','version']))
```

Step 2:在維運機上執行它 “check-openssl-version.spy” 並得到輸出報表

```jsx
$ sshscript check-openssl-version.spy
host     version
-------  --------------------------------
host1    OpenSSL 1.0.2k-fips  26 Jan 2017
host2    OpenSSL 1.1.1k  FIPS 25 Mar 2021
host3    OpenSSL 1.1.1n  15 Mar 2022
host4    OpenSSL 1.1.1o  3 May 2022
host5    OpenSSL 1.0.2g  1 Mar 2016
```

進一步,你可以把常用的設定獨立成另一個檔案。以下演示這個作法。

首先建立一個新檔案，名為 “common.spy”，內容是常用的參數。

```jsx
#file: common.spy
hosts = ['host1','host2','host3','host4','host5']
user = 'your-name'
password = 'your-secret'
```

接下來，改寫上面那個 check-openssl-version.spy 檔案的內容，如下：

```jsx
# file: check-openssl-version.spy

# collect
$.include('common.spy')  # ⬅ 重點在這行，呼叫 $.include()
opensslVersions = []
for host in hosts:
    with $.connect(f'{username}@{host}',password=password) as _:
        $openssl version
        opensslVersions.append([host,$.stdout])
# output
from tabulate import tabulate
print(tabulate(opensslVersions, headers=['host','version']))
```

這樣一來，當你改密碼時，就算你有100個像是check-openssl-version.spy的程式檔案，也只要更改common.spy就可以。

還有一個好消息，你可以在$命令列當中使用Python的變數。 以check-openssl-version.spy為例，只要稍微改個地方就可以察看其他程式的版本。例如：

```python
# file: check-openssl-version.spy

# collect
$.include('common.spy')  
opensslVersions = []
appName = 'openssl'  # ⬅ 把指令做成變數
for host in hosts:
    with $.connect(f'{username}@{host}',password=password) as _:
        # ⬇ 重點在這裡, 執行時 appName 會被取代成 "openssl"
        # 關鍵是在＄的內容中，可以用@{}植入Python的變數敘述
        $@{appName} version    
        opensslVersions.append([host,$.stdout])
            
# output
from tabulate import tabulate
print(tabulate(opensslVersions, headers=['host','version']))
```

當然，與check-openssl-version.spy檔案相同結構的程式檔案為例，你可以用$執行其他shell的命令。例如”df”

```python
#蒐集每個主機的硬碟用量
$.include('common.spy')  
for host in hosts:
    # connect to this host
    with $.connect(f'{username}@{host}',password=password) as _:
        # 以下這行執行shell的指令 "df"
        $df
        # parse the result in python
        for line in $.stdout.split('\n'):
            cols = line.split()
            partition = cols[0]
            capacity = cols[4][:-1] # drop "%"
            if int(capacity) > 80:
                print(f'Caution:{partition} need help')

```

# 應用情境二

假設你的維運機（跳板機）在雲端。 像是上面的例子當中，common.spy 這個檔案內有可以登入所有主機的密碼，放在雲端主機上有點危險。你想把那個檔案放在公司內的主機上比較安全。那麼，你可以這麼做：

首先在辦公室的安全主機上建立一個檔案，名為 “secret.spy” ，把密碼放在這裡。

```jsx
#file: 辦公室的安全主機上的檔案 “secret.spy” 的內容
password = ‘your-secret’
```

其次，把維運主機（在雲端）上的 common.spy 改成這樣：

```jsx
#file: 雲端維運主機上common.spy 的內容
hosts = ['host1','host2','host3','host4','host5']
user = 'your-name'
# ⬇ 重點在這裡
$.include('secret.spy')
```

然後，在辦公室的安全主機上，建立一個新檔案，名為 “run-from-trusted-host.spy” 

```jsx
# file: 辦公室的安全主機上的檔案 “run-from-trusted-host.spy” 的內容

# ssh 到維運機（跳板機）
$.connect('you@maintaining-host',password='password')

# 假設 secret.spy 在安全機的 /home/my/ 目錄
# 假設 common.spy 在維運機的 /home/you/project/ 目錄
# 把 secret.spy上傳到維運機
$.upload('/home/my/secret.spy','/home/you/project/secret.spy')

# 在維運機上執行 check-openssl-version.spy ，它會include common.spy
# common.spy 會include secret.spy，裡面有密碼
$sshscript check-openssl-version.spy

# 執行結束後把secret.spy刪除
$rm /home/you/project/secret.spy

```

直接在辦公室的安全主機上執行 “run-from-trusted-host.spy” 

```python
$sshscript run-from-safe-host.spy
```

這樣你就不需要把密碼放在雲端主機裡面。

當然，你也可以把secret.spy改成這樣：

```
#file: 辦公室的安全主機上的檔案 “secret.spy” 的內容
from getpass import getpass
password = getpass()
```

這樣一來，你只需要把密碼放在心底。只是run-from-safe-host.spy必須手動執行，再也不能用cron執行而已。
