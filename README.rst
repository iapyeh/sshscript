
.. _h60505595954b5b1b3159693b175140:

SSHScript
#########

The sshscript is an integration of subprocess and \ |LINK1|\ . It provides an unique interface to invoke commands locally and remotely. Something likes to embed shell commands in a python script. For example:


.. code:: 

    # execute a command on localhost and parse the output 
    $ls -l
    for line in $.stdout.split('\n'):
        if line.startswith('d'): continue
        print(line)


.. code:: 

    # execute a command on remote host and parse the output 
    @open('user@host')
    $ls -l
    for line in $.stdout.split('\n'):
       if line.startswith('d'): continue
       print(line)

.. _h7c2856e31346c6c7732740396a6867:

Installation
============


.. code:: 

    pip install sshscript

.. _h36711971261f3518968783337294a20:

Tutorial
========

.. _h2c1d74277104e41780968148427e:




.. _h6e172a227d553419513e7a1117648072:

Syntax
======


.. bottom of content


.. |LINK1| raw:: html

    <a href="https://www.paramiko.org/" target="_blank">paramiko</a>

