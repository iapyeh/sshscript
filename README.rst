
.. _h60505595954b5b1b3159693b175140:

SSHScript
#########

The sshscript is an integration of subprocess and \ |LINK1|\ . It provides an unique interface to invoke commands locally and remotely. Something likes to embed shell commands in a python script. For example:


.. code:: 

    $ls -l
    for line in $.stdout.split('\n'):
        if line.startswith('d'): continue
        print(line)


.. bottom of content


.. |LINK1| raw:: html

    <a href="https://www.paramiko.org/" target="_blank">paramiko</a>

