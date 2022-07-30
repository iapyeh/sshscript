SSHScript
#########

The sshscript is an integration of subprocess and paramiko_ . 
It provides an unique interface to invoke commands locally and remotely. 
Something likes to embed shell commands in a python script. For example:

.. code:: 

    # file: demo.spy
    # execute a command on localhost and parse the output with python
    $netstat -ant
    for line in $.stdout.split('\n'):
        if not line.endswith('LISTEN'): continue
        print(line)

    # file: demo.spy
    # by adding one line to make connection.
    # you can do the same thing on remote host-a
    $.connect('user@host-a',password='19890604')
    $netstat -ant
    for line in $.stdout.split('\n'):
        if not line.endswith('LISTEN'): continue
        print(line)

    # file: demo.spy
    # by adding two lines to make connections.
    # you can do the same thing on remote host-b which is behind host-a
    $.connect('user@host-a',password='19890604')
    $.connect('user@host-b',password='19890604')
    $netstat -ant
    for line in $.stdout.split('\n'):
        if not line.endswith('LISTEN'): continue
        print(line)

Execution

.. code::

    $ sshscript demo.spy

Installation
============

.. code:: 

    $ pip install sshscript

Documents
=========

Here is documents_



.. _paramiko : https://www.paramiko.org/

.. _documents: https://iapyeh.github.io/sshscript/index
