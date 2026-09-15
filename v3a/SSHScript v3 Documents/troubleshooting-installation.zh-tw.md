---
title: "安裝疑難排解 (zh-TW)"
parent: "SSHScript v3.1 Documentation"
nav_order: 10
---

# 安裝疑難排解 (zh-TW)

SSHScript v3.1 需要 Python 3.9 以上版本。安裝與執行時使用同一個 Python
直譯器，可以避免多數環境問題。

## 確認 Python 與 pip

```sh
python3 --version
python3 -m pip --version
```

若 Python 低於 3.9，請安裝受支援的版本並建立新的虛擬環境。

## 在虛擬環境安裝

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install sshscript
```

虛擬環境可以避免系統套件權限問題，也能明確確保 Python 與 `pip`
屬於同一套環境。

## 找不到 `sshscript` 命令

先確認套件是否安裝在目前的直譯器：

```sh
python3 -m pip show sshscript
python3 -m pip install --upgrade sshscript
```

若套件存在但命令仍找不到，請啟用虛擬環境，或把該 Python 的 scripts
目錄加入 `PATH`。優先使用 `python3 -m pip`，不要假設 `pip` 與
`python3` 一定指向同一套安裝。

## 匯入了錯誤版本

```sh
sshscript --version
python3 -c "import sshscript; print(sshscript.__version__); print(sshscript.__file__)"
```

舊的原始碼目錄、本地 `sshscript.py`，或另一個虛擬環境都可能遮蔽已安裝
的套件。請離開含有同名模組的目錄，並檢查 `sshscript.__file__`。

若要使用目前 checkout 進行開發：

```sh
python3 -m pip install -e .
```

## 相依套件或建置錯誤

先升級 Python 打包工具，再重新安裝：

```sh
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install --upgrade sshscript
```

若仍失敗，請記錄 Python 版本、作業系統與完整的套件管理錯誤訊息。公開
回報中不可包含帳號密碼、私人金鑰或其他秘密。

## 安裝後出現 host-key 錯誤

`unknown host key` 或 `host key changed` 表示安裝已成功，但 SSHScript
的安全連線政策拒絕未驗證的伺服器。請先確認伺服器身分，再更新
`known_hosts`；不要把關閉驗證當成一般解法。詳見
[`Session.connect()`](Basic/connect)。

## 最小診斷資訊

```sh
python3 --version
python3 -m pip --version
python3 -m pip show sshscript
sshscript --version
```

只有在受保護的除錯環境才使用 `--traceback`，因為完整 traceback
可能包含程式碼、命令、路徑或秘密。

Last Updated: 2026-09-14 18:02:02
