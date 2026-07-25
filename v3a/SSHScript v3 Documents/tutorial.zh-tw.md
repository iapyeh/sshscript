---
title: "SSHScript v3.0 Tutorial (zh-TW)"
parent: "SSHScript v3 Documents"
nav_order: 2
---

# SSHScript v3.0 Tutorial (zh-TW)

SSHScript 讓你把熟悉的系統指令直接寫進 Python，並以同一套程式處理本機、遠端主機與巢狀 SSH 連線。

它的目的不是取代 shell，也不是把維運流程改寫成另一套宣告格式；它要保留工程師已經熟悉、經過驗證的指令，再把連線、流程控制、資料處理、例外處理與 Python 生態系接在一起。

一個 SSHScript 程式通常反覆進行三件事：

1. 在本機或遠端主機執行指令。
2. 從 `$.stdout`、`$.stderr`、`$.exitcode` 取得結果。
3. 用 Python 判斷、整理資料，決定下一個動作。

這份教學以 SSHScript v3.0 的 dollar syntax 為主，範例檔案使用慣例副檔名 `.spy`。

## 1. 安裝與執行

安裝或升級 SSHScript：

```sh
python3 -m pip install --upgrade sshscript
```

確認版本：

```sh
sshscript --version
```

建立 `hello.spy`：

```python
$hostname
print(f"這台主機是 {$.stdout.strip()}")
```

執行：

```sh
sshscript hello.spy
```

`.spy` 裡仍然是 Python；`if`、`for`、函式、類別、例外處理與第三方套件都可以照常使用。SSHScript 只增加以 `$` 開頭的指令語法，以及管理本機或 SSH session 的能力。

## 2. 第一個實用程式：檢查多台主機

假設你需要盤點多台主機的 OpenSSL 版本。手動做法是逐台登入、執行指令、複製結果；SSHScript 則把原本的操作直接放進 Python 流程：

```python
# check-openssl.spy
from getpass import getpass

accounts = [
    "ops@host1.example.net",
    "ops@host2.example.net",
    "ops@host3.example.net",
]
password = getpass("SSH password: ")
report = []

for account in accounts:
    with $.connect(account, password=password):
        $openssl version
        report.append({
            "host": account,
            "version": $.stdout.strip(),
            "exitcode": $.exitcode,
            "error": $.stderr.strip(),
        })

for row in report:
    if row["exitcode"] == 0:
        print(f'{row["host"]}: {row["version"]}')
    else:
        print(f'{row["host"]}: ERROR: {row["error"]}')
```

`with $.connect(...)` 之內的 dollar command 在遠端執行；離開區塊後，自動回到原來的 session。這個「目前有效 session」的概念，是 SSHScript 的核心。

## 3. 單 `$`：執行指令與 shell 功能

SSHScript v3 以單 `$` 作為統一的指令語法。它會以 quote-aware 的方式檢查指令：一般 OS 指令以直接模式執行；遇到管線、重導向、控制運算子或未加引號的 shell 變數時，會自動改用 shell 模式。不需要再為 shell 功能改寫成雙 `$$`。

```python
$python3 -c "print('hello')"

assert $.stdout.strip() == "hello"
assert $.stderr == ""
assert $.exitcode == 0
```

### 3.1 v3.0 支援的指令形式

可以直接寫指令：

```python
$hostname
```

也可以使用一般字串或 raw string：

```python
$'printf hello'
$r'printf raw-string'
```

用 f-string 插入 Python 值：

```python
name = "sshscript"
$f'python3 -c "print(\'{name}\')"'
```

或用括號執行由 Python 產生的完整指令：

```python
command = "python3 -c \"print('dynamic command')\""
$(command)
```

括號形式也能傳入執行選項：

```python
$("python3 -c \"print('done')\"", timeout=5)
```

當變數來自使用者或外部資料時，不要未經檢查就把它拼成指令。能固定參數就固定參數；需要 shell quoting 時，使用 `shlex.quote()`。

### 3.2 取得與保存結果

每次 dollar command 執行後，都可讀取：

- `$.stdout`：標準輸出。
- `$.stderr`：標準錯誤。
- `$.exitcode`：結束碼，成功通常為 `0`。

```python
$python3 -c "import sys; print('out'); sys.stderr.write('err\\n'); sys.exit(7)"

print($.stdout)
print($.stderr)
print($.exitcode)
```

也可以直接接收 stdout 與 stderr：

```python
stdout, stderr = $python3 -c "print('captured')"
print(stdout.strip())
```

`$.stdout`、`$.stderr` 與 `$.exitcode` 會在下一次指令執行後更新。若稍後還要使用某次結果，請立即存進自己的變數：

```python
$hostname
hostname = $.stdout.strip()

$whoami
username = $.stdout.strip()

print(hostname, username)
```

### 3.3 自動使用 shell 功能

管線、重導向、shell 變數、萬用字元與多行 shell script 都可以直接使用單 `$`。SSHScript 會自動選擇 shell 模式：

```python
$printf 'alpha\nbeta\n' | grep beta
assert $.stdout.strip() == "beta"
```

動態指令同樣會自動判斷：

```python
pipeline = "printf dynamic | tr a-z A-Z"
$(pipeline, timeout=5)
assert $.stdout == "DYNAMIC"
```

一般字串與 raw string 仍可照常使用；不含 shell 語法時會採直接模式：

```python
$'printf string-direct'
$r'printf raw-direct'
```

f-string 與多行 shell script 也可以直接使用：

```python
import shlex

folder = "/tmp/sshscript tutorial"
path = f"{folder}/result.txt"

$f'''mkdir -p {shlex.quote(folder)}
printf 'line-1\nline-2\n' > {shlex.quote(path)}
tail -n 1 {shlex.quote(path)}'''

assert $.stdout.strip() == "line-2"
```

若指令內容本身無法可靠地呈現意圖，可以明確指定模式：

```python
# 把 | 當成一般參數，而不是 pipe。
$("python3 -c \"import sys; print(sys.argv[1:])\" '|' cat", shell=False)

# 強制使用 POSIX shell；也可以指定 shell="bash"。
$("printf forced-shell", shell=True)
$("printf bash-shell", shell="bash")
```

`$$` 僅保留給舊程式相容使用，已在 v3 中 deprecated；新程式應只使用單 `$`。

## 4. v3.0 的 Python 相容性

SSHScript v3.0 以 Python token 為基礎辨識 dollar syntax。一般 Python 字串、raw string、f-string 的文字區與註解中的 `$` 不會被當成指令：

```python
literal = "$.stdout $echo $$echo"
home_text = r"$HOME"
doubled_braces = f"literal={{$.stdout}}"

assert literal == "$.stdout $echo $$echo"
assert home_text == r"$HOME"
assert doubled_braces == "literal={$.stdout}"
```

Dollar command 也可以放進 Python 函式，函式會在呼叫當下的有效 session 上執行：

```python
def hostname():
    $hostname
    if $.exitcode != 0:
        raise RuntimeError($.stderr)
    return $.stdout.strip()

print("local:", hostname())

with $.connect("ops@remote.example.net"):
    print("remote:", hostname())
```

這種寫法讓「要做什麼」與「在哪一台主機做」彼此分離，同一個函式可重複套用到本機或不同遠端主機。

## 5. 持續存在的 shell：`with $`

每個獨立的 `$command` 都是一次指令執行。如果多個指令必須共享目前目錄、shell 變數或 shell 狀態，使用 `with $`：

```python
with $ as shell:
    $STATE=kept
    $cd /tmp
    $printf '%s:%s' "$STATE" "$PWD"

    assert $.stdout == "kept:/tmp"
    assert shell.exitcode == 0
```

可以明確指定 shell：

```python
with $('bash') as shell:
    $printf 'running in bash'
```

Shell 名稱也能由 Python 動態決定：

```python
shell_command = "bash"
with $f'{shell_command}' as shell:
    $printf 'dynamic shell'
```

也可以使用 shebang 形式：

```python
with $#!/usr/bin/env bash as shell:
    $cd /tmp
    $pwd
    assert $.stdout.strip() == "/tmp"
```

完整寫法是 `$.shell(...)`：

```python
with $.shell('bash') as shell:
    $PERSISTED=hello
    $printf '%s' "$PERSISTED"
```

`with` 區塊可巢狀使用；離開內層 console 後，外層 shell 會恢復成有效 session。

## 6. 遠端與巢狀 SSH 連線

使用帳號與密碼：

```python
with $.connect("user@host.example.net", password="secret") as remote:
    $hostname
    print($.stdout.strip())
```

如果已設定 SSH key，通常不必提供密碼：

```python
with $.connect("user@host.example.net"):
    $uptime
```

指定 key 檔：

```python
with $.connect(
    "user@host.example.net",
    pkey_path="/absolute/path/to/id_rsa",
):
    $whoami
```

SSHScript 支援從目前遠端 session 再連到下一台主機：

```python
with $.connect("ops@jump.example.net"):
    $hostname
    jump_host = $.stdout.strip()

    with $.connect(
        "admin@internal.example.net",
        pkey_path="/home/ops/.ssh/id_rsa",
    ):
        $hostname
        internal_host = $.stdout.strip()

    # 已回到 jump host
    $whoami

# 已回到 localhost
print(jump_host, internal_host)
```

把連線寫成 `with` 區塊可以清楚表達 session 的生命週期，也可確保發生例外時執行清理。

## 7. 互動式程式：`$.enter()`

需要 prompt、輸入與等待特定輸出的程式，例如 Python REPL、資料庫 console 或設備 CLI，可使用 `$.enter()`：

```python
with $.enter(
    "python3 -q",
    prompt=">>>",
    exit=chr(4),       # Ctrl-D
) as console:
    $("print('first line')")
    $.expect("first line")

    $.input("print('second line')")
    $.expect("second line")

    assert "second line" in console.stdout
```

常用操作：

- `$.input(text)`：送出輸入。
- `$.expect(pattern)`：等待指定文字或 pattern。
- `$.wait_for_silent(seconds)`：等待輸出安靜一段時間。
- `$.clear()`：清除目前累積的輸出 buffer。

互動程式的 prompt 與退出方式各不相同，應依實際程式設定 `prompt`、`expect` 與 `exit`，並為可能卡住的操作規劃 timeout。

## 8. sudo 與 su

需要提升權限時，用 context manager 明確界定範圍：

```python
from getpass import getpass

password = getpass("sudo password: ")

with $.sudo(password=password):
    $whoami
    assert $.stdout.strip() == "root"
```

切換使用者：

```python
with $.su("service-user", password="secret"):
    $whoami
    assert $.stdout.strip() == "service-user"
```

不要把真實密碼提交到版本控制。可使用 `getpass()`、環境變數或組織既有的 secret 管理方式取得憑證。

## 9. 上傳與下載

遠端 session 可使用 SFTP 上傳與下載檔案：

```python
with $.connect("user@host.example.net") as remote:
    remote.upload("config.ini", "/tmp/config.ini")
    remote.download("/var/log/app.log", "app.log")
```

路徑方向要以執行 `.spy` 的本機為準：

- `upload(local_source, remote_destination)`
- `download(remote_source, local_destination)`

若下一步要把檔案移到只有 root 能寫入的位置，可先上傳至一般使用者可寫入的目錄，再進入 `$.sudo()` 執行 `install` 或 `mv`。

## 10. 直接匯入 `.spy` 模組

SSHScript v3.0 可以像 Python 模組一樣匯入另一個 `.spy` 檔。這適合把可重用的檢查或操作拆成小函式。

建立 `server_checks.spy`：

```python
def kernel_release():
    $uname -r
    if $.exitcode != 0:
        raise RuntimeError($.stderr)
    return $.stdout.strip()
```

在 `inventory.spy` 使用：

```python
from server_checks import kernel_release

print("local:", kernel_release())

with $.connect("ops@host.example.net"):
    print("remote:", kernel_release())
```

模組中的 dollar command 同樣使用呼叫端當下的有效 session，因此很適合建立自己的維運函式庫。

## 11. 多執行緒與有效 session

每個執行緒都有自己的 session stack。新連線進入 stack 頂端，離開 `with` 區塊後回到上一層，所以不同執行緒可以同時在不同主機工作。

```python
import threading

accounts = [
    "ops@host1.example.net",
    "ops@host2.example.net",
    "ops@host3.example.net",
]
results = {}
lock = threading.Lock()

def collect(account):
    with $.connect(account):
        $uptime
        row = ($.exitcode, $.stdout.strip(), $.stderr.strip())
    with lock:
        results[account] = row

threads = [threading.Thread(target=collect, args=(account,))
           for account in accounts]

for thread in threads:
    thread.start()
for thread in threads:
    thread.join()

for account, row in results.items():
    print(account, row)
```

實務上請注意：

- 每個工作執行緒自行建立或明確進入它要使用的 session。
- 多個執行緒共用 Python 容器時仍須使用 `Lock` 或其他同步機制。
- worker 內的例外應收集並在主執行緒重新拋出，避免失敗只出現在背景輸出中。
- 設定合理的連線與指令 timeout。

## 12. 在一般 Python 程式使用 SSHScript

若專案不想使用 dollar syntax，也可以直接使用 v3 的 `Session` API：

```python
import sshscript

session = sshscript.Session()

session("hostname")
print(session.stdout.strip())

session("printf 'a\\nb\\n' | tail -n 1")
print(session.stdout.strip())

with session.connect("ops@host.example.net") as remote:
    remote("uptime")
    print(remote.stdout.strip())
```

兩種寫法的概念相同：

- `$command` 對應 `session(command)`，兩者都會自動選擇直接或 shell 模式。
- `$(command, shell=False)` 可強制直接模式；`$(command, shell=True)` 或 `shell="bash"` 可強制 shell 模式。
- `with $` 對應 `with session.shell()`。
- `$.stdout` 對應 `session.stdout`，其餘結果屬性亦同。

Dollar syntax 適合讓維運步驟一眼可讀；`Session` API 則適合整合既有 Python 專案。

## 13. 完整範例：找出磁碟使用率過高的主機

下面的程式保留系統工程師熟悉的 `df` 指令，再使用 Python 做資料整理與判斷：

```python
# disk-report.spy
accounts = [
    "ops@host1.example.net",
    "ops@host2.example.net",
]
threshold = 80
warnings = []

def check_disk(account):
    $df -P
    if $.exitcode != 0:
        return [{
            "host": account,
            "filesystem": None,
            "usage": None,
            "error": $.stderr.strip(),
        }]

    rows = []
    for line in $.stdout.splitlines()[1:]:
        columns = line.split()
        if len(columns) < 6 or not columns[4].endswith("%"):
            continue
        usage = int(columns[4][:-1])
        if usage >= threshold:
            rows.append({
                "host": account,
                "filesystem": columns[0],
                "usage": usage,
                "mountpoint": columns[5],
                "error": None,
            })
    return rows

for account in accounts:
    try:
        with $.connect(account):
            warnings.extend(check_disk(account))
    except Exception as exc:
        warnings.append({
            "host": account,
            "filesystem": None,
            "usage": None,
            "error": str(exc),
        })

if not warnings:
    print(f"所有檔案系統使用率都低於 {threshold}%")
else:
    for row in warnings:
        if row["error"]:
            print(f'{row["host"]}: ERROR: {row["error"]}')
        else:
            print(
                f'{row["host"]}: {row["filesystem"]} '
                f'掛載於 {row["mountpoint"]}，使用率 {row["usage"]}%'
            )
```

這個例子呈現 SSHScript 的主要精神：指令負責取得系統事實，Python 負責流程、結構化資料、判斷與錯誤處理，而 `$.connect()` 只決定同一套工作要在哪裡執行。

## 14. 除錯與常見陷阱

顯示執行時輸出：

```sh
sshscript --verbose example.spy
```

顯示轉換後的 Python，不執行程式：

```sh
sshscript --script example.spy
```

啟用除錯資訊：

```sh
sshscript --debug example.spy
sshscript --debug 8 example.spy
```

撰寫程式時，建議特別留意：

1. `$.stdout` 等結果會被下一個指令更新，需要時立即保存。
2. Pipe、redirect 與未加引號的 `$HOME` 會自動使用 shell；若要表達字面的 `$HOME`，請加上引號或跳脫 `$`。必要時可用 `shell=False` 或 `shell=True` 明確指定。
3. Python 值插入 shell 指令時使用 f-string，外部值再以 `shlex.quote()` 處理。
4. 遠端連線、sudo、shell 與互動 console 優先使用 `with` 管理生命週期。
5. 不要把密碼或 private key 內容寫進程式庫。
6. 先用單一主機驗證指令與 parser，再擴展成多主機或多執行緒。

## 結語

SSHScript v3.0 把 shell 擅長的「直接操作系統」和 Python 擅長的「程式結構與資料處理」放在同一個檔案裡。你不必放棄既有指令，也不必先學一套新的任務描述語言；從一行 `$hostname` 開始，加上 `$.connect()`，同一段可讀的 Python 程式就能逐步成長為本機、遠端、巢狀連線與平行作業的自動化工具。

Last Updated: 2026-07-25 16:59:40
