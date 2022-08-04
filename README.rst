
SSHScript
#########

The sshscript is an integration of subprocess and _paramiko . It provides an unique interface to invoke commands locally and remotely. Something likes to embed shell commands in a python script. For example:


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

    pip install sshscript


Why
===

* Easy to use, quick to learn. you can utilize the power of subprocess and Paramiko to execute commands and make ssh connections even having no idea of both.

* Embedding shell commands in Python scripts are intuitive and self-explaining. It is good for teamwork and maintenance.

* Handling execution output or exceptions with Python is easier than shell script. Tons of Python packages are handy for you.


More
====

* docs_

* Examples_

<<<<<<< HEAD
* Release Notes_
=======
* \ |LINK4|\ 

.. bottom of content
>>>>>>> affb2040abd6207330cdd0eb5e45f790a7c50f5d

.. bottom of content

.. _paramiko : https://www.paramiko.org/

.. _docs : https://iapyeh.github.io/sshscript/index

.. _Examples : https://iapyeh.github.io/sshscript/examples/index


.. _Notes : https://iapyeh.github.io/sshscript/releasenotes

.. |LINK4| raw:: html

    <a href="https://iapyeh.github.io/sshscript/releasenotes" target="_blank">Release Notes</a>

