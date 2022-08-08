
SSHScript
#########

SSHScript makes Python become a scripting tool for system automation. Functionally, the SSHScript is something like the Ansible. Instead of writing descriptive YML files, just write Python scripts with the simplicity of Python and the power of all Python packages.

Technically, the SSHScript is an integration of subprocess and Paramiko . It provides an unique interface to invoke commands locally and remotely. Something like embedding shell commands in a python script.

Below are three examples:


.. code:: 

    # example 1: demo.spy
    # execute a command on localhost and parse the output with python
    $netstat -ant
    for line in $.stdout.split('\n'):
        if not line.endswith('LISTEN'): continue
        print(line)

    # example 2: demo.spy
    # by adding one line to make connection.
    # you can do the same thing on remote host-a
    $.connect('user@host-a',password='19890604')
    $netstat -ant
    for line in $.stdout.split('\n'):
        if not line.endswith('LISTEN'): continue
        print(line)

    # example 3: demo.spy
    # by adding two lines to make connections.
    # you can do the same thing on remote host-b which is behind host-a
    $.connect('user@host-a',password='19890604')
    $.connect('user@host-b',password='19890604')
    $netstat -ant
    for line in $.stdout.split('\n'):
        if not line.endswith('LISTEN'): continue
        print(line)



Execution
=========

.. code:: 

    $ sshscript demo.spy

Installation
============


.. code:: 

    pip install sshscript


Why and Features
================

The idea is that many automation tasks are running commands and dealing with outputs on localhost and remote hosts. Among these scripts, there are many common routines. Eg. making ssh connections, execution and collecting data. That's where the SSHScript comes into play. The most charming part is that you could directly process the resulting data in Python. It then enables you to efficiently build complex data structures and processing flow with object-oriented approaches.

* Easy to script. If you know what commands to run and which host to ssh, then you can write your script. No extra stuff to learn.

* Embedding shell commands in Python scripts are intuitive and self-explaining. It is good for teamwork and maintenance.

* Handling execution output or exceptions with Python is easier than shell script.

* Your scripts are powered by tons of Python packages.

* With thread support.

More
====

* docs_

* Examples_

* Release Notes_

.. bottom of content

.. _paramiko : https://www.paramiko.org/

.. _docs : https://iapyeh.github.io/sshscript/index

.. _Examples : https://iapyeh.github.io/sshscript/examples/index


.. _Notes : https://iapyeh.github.io/sshscript/releasenotes
