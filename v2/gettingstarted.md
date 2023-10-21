# SSHScript v2.0 Getting Started (Draft)

Last Updated on 2023/10/21

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

## Installation
    ```
        pip3 install sshscript
        ## or
        python3 -m pip install sshscript
    ```
## Upgrading
    ```
        pip3 install sshscript --upgrade
        ## or
        python3 -m pip install sshscript --upgrade
    ```
    
## 🔵 <a name="one-dollar"></a>Check Installation

## Check Installation

After you have installed the SSHScript. let us check if it works. The SSHScript would install a cli named "sshscript". You can open a console and typing "sshscript" to check if it works.

```
$ sshscript
```

If it works, you would have screen like below:
(image of "sshscript")

If you don't have that screen, you might have to modify the PATH environment variable
of your shell. You can find the path of "sshscript" by running the following command:

```
$ python3 -c 'import sysconfig; print(sysconfig.get_path("scripts"))'
```