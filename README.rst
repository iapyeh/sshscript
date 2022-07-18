SSHScript
#########

The sshscript is an integration of subprocess and paramiko_ . 
It provides an unique interface to invoke commands locally and remotely. 
Something likes to embed shell commands in a python script. For example:

.. code:: 

    # execute a command on localhost and parse the output with python
    $ls -l
    for line in $.stdout.split('\n'):
        if line.startswith('d'): continue
        print(line)
    
    # execute a command on remote host and parse the output with python
    $.open('user@host')
    $ls -l
    for line in $.stdout.split('\n'):
        if line.startswith('d'): continue
        print(line)

More on github_



.. _paramiko : https://www.paramiko.org/

.. _github: https://github.com/iapyeh/sshscript