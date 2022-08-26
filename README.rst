

Announcement
############

v1.1.14 has released on 2022/8/24. Users are recommanded to upgrade by 

.. code::

    pip3 install --upgrade sshscript


+---------------------------------------------------------------------------------------------------+
|For installers of version v1.101, v1.102 and v1.103.  Please do upgrade with                       |
+---------------------------------------------------------------------------------------------------+
.. code:: 

    python3 -m pip install sshscript==1.1.14
    
Please see v1.1.14 Relaese Notes_ for details.
    
SSHScript
#########
System automation is a process of realizing management logics by repeating networking and execution. SSHScript makes Python an easy tool for creating system automation processes. With syntax sugar of SSHScript, writing python scripts to execute commands on local host or remote hosts is easy.

You just need to embed commands and networking in python scripts. SSHScript would execute them and let you handle outputs all in Python. You need not know programming about the subprocess module and Paramiko(ssh).

Technically, SSHScript is an integration of the subprocess and Paramiko. It provides an unique interface to invoke commands on local host and remote hosts. It could perform the same functionality as a shell script. But it is pure Python.

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

* SSHScript supports thread, aka jobs in parallel.

Releases
========

The last version is 1.1.14. (2022/8/24). Relase Notes_

More
====

* docs_

* Examples_


.. bottom of content

.. _paramiko : https://www.paramiko.org/

.. _docs : https://iapyeh.github.io/sshscript/index

.. _Examples : https://iapyeh.github.io/sshscript/examples/index


.. _Notes : https://iapyeh.github.io/sshscript/release-v1.1.14
