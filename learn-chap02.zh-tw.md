<div style="text-align:right"><a href="./index">Index</a></div>
# SSHScript使用教學 第二章

在第一章介紹了執行指定的語法$，及得到執行結果的 $.stdout與$.stderr。以及連線到遠端執行指令的 $.connect()。那是很典型的用法，如果還沒看過，請務必先去看完再來閱讀第二章。

其實SSHScript並不複雜，第一章所介紹的已經是SSHScript 90％的核心功能。但是因為世事複雜，不得不衍生出第二章的功能。我們先看看問題在哪裡，這樣你就知道第二章存在的原因，學起來很快就懂。

## Two-dollars Command

把第一章的例子稍微改一下：

```
# 這是hello.spy檔案的內容
$ echo hello `whoami`
print($.stdout)
```

例如，假設你的帳號是 john，你預期輸出會是：

```
hello john
```

你會發現，他的輸出跟你所想的不一樣，而是：

```
hello `whoami`
```

平常shell默默幫我們做了很多事，只是我們無感。你認為輸出是 hello john是因為`whoami`先被shell執行得到john的結果之後才送給echo去執行。換言之，如果要得到你預期的結果，需要一個shell來執行那行指令，而不是直接叫OS執行那行指令。

SSHScript讓你簡單就做這件事。如果你要呼叫shell來執行你的指令，就這麼做：

```
# 這是hello.spy檔案的內容
$$ echo hello `whoami`
print($.stdout)
```

很簡單，一個$不夠，那就用兩個$$。

其實像是 | (pipe), > (redirect), $PATH 這些都是shell提供的功能。所以，如果你執行的指令用了那些shell才有的功能時，須使用$$的語法。

我最常用到$$是在sudo的時候。例如：

```
$$echo my-password | sudo -S ls -l /root
```

## 多列 Two-dollars Command

跟\$不一樣的地方是，\$\$的多列指令模式有「脈絡」的概念。簡單講，它知道自己所在的目錄。在$的多行字串模式中，如果需要提供路徑當執行參數，必須提供絕對路徑才不會有怪問題。但是在$$時，因為有shell在，使用相對路徑通常可以得到你所想要的結果。例如：

```
$.connect('username@host')
$$'''
cd /tmp
ls -l *.txt
rm *.txt
'''
```

在上例當中，因為一開始就 cd /tmp，所以第二行的命令 ls 所列出來的是 /tmp目錄下的txt檔案，第三行的命令 rm 所刪掉的也是 /tmp目錄下的 txt檔案。這是因為$$是在shell當中執行的指令。

如果不是$$，而是$的話，雖然有cd /tmp，但因為使用的是相對路徑，因此被第三行指令刪除的是一開始登入那台主機時的目錄內的txt檔案，一般而言是登入帳號的home directory。

刪錯檔案通常是一場悲劇，這裡只是為了演示$$的功能，盡量還是使用絕對目錄是比較穩當的作法。

## with

既然有shell，那麼就有interactive shell的情況。SSHScript也支援這樣的用法，例如，以下這段程式模擬執行sudo su，輸入密碼之後成為root，然後執行whoami與ls -l /root兩個指令。

```
with $$sudo -S su as console:
    console.sendline('my-password')
    console.sendline('''
         whoami
         ls -l /root
         ''')
```

with … as 是典型的Python語法。當你使用with在$$前面時，可以從 as 後面得到一個console變數，利用console變數，可以跟負責執行程式的shell互動。

在Python當中，執行互動應用最棒的是pexpect模組，SSHScript在此借用一部分他的函式名稱，像是sendline(), expect()。

sendline()就是輸入一行，像是一般在console時所做的那樣，有可能是提供密碼，或者執行一行程式。同樣的，你可以得到執行程式之後的stdout與stderr輸出。例如：

```
with $$sudo -S su as console:
    console.sendline('my-password')
    
    console.sendline('ls -l /root')
    # console.stdout會有ls的stdout輸出
    for line in console.stdout.split('\n'):
         print(line.split())

    console.sendline('whoami')
    # 此處的console.stdout是whoami的輸出內容
    assert console.stdout.strip() == 'root'

# 離開with之後，$.stdout的內容是在with當中所有執行的指令在stdout的輸出
$.stdout
# 離開with之後，$.stderr的內容是在with當中所有執行的指令在stderr的輸出
$.stderr
```

因為with本身的意義已經很明確，如果你使用with語法的話，接$或$$都可以。例如，以下的例子，一樣是得到一個可以互動的shell。

```
with $sudo -S su as console:
    console.sendline('my-password')
    console.sendline('whoami')
```
