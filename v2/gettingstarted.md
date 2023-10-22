# SSHScript v2.0 Getting Started (Draft)

Last Updated on 2023/10/21

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Topics

## 🔵 Installation
```
    pip3 install sshscript
    ## or
    python3 -m pip install sshscript
```

## 🔵 Upgrading
```
    pip3 install sshscript --upgrade
    ## or
    python3 -m pip install sshscript --upgrade
```
    
## 🔵 <a name="check-installation"></a> Checking if SSHScript is Installed

Once you have installed SSHScript, you can check if it is working by running the sshscript command in a terminal.

```
$ sshscript
```

If SSHScript is installed correctly, you will see a screen like this:

![image](sshscriptcli.png)

If you do not see this screen, you may need to modify your shell's PATH environment variable to include the path to the SSHScript CLI. You can find the path to the SSHScript CLI by running the following command:

```
$ python3 -c 'import sysconfig; print(sysconfig.get_path("scripts"))'
```
Once you have the path to the SSHScript CLI, you can add it to your PATH environment variable. For example, to add the path to your PATH environment variable in Bash, you would run the following command:

```
export PATH=$PATH:/path/to/sshscript
```

Once you have added the path to your PATH environment variable, you should be able to run the sshscript command from anywhere in your terminal.
