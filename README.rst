
.. _h60505595954b5b1b3159693b175140:

SSHScript
#########

The sshscript is an integration of subprocess and \ |LINK1|\ . It provides an unique interface to invoke commands locally and remotely. Something likes to embed shell commands in a python script. For example:


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

.. _h7c2856e31346c6c7732740396a6867:

Installation
============


.. code:: 

    pip install sshscript

.. _h6f164770434487734563451612a1218:

Why
===

* Easy to use, quick to learn. you can utilize the power of subprocess and Paramiko to execute commands and make ssh connections even having no idea of both.

* Embedding shell commands in Python scripts are intuitive and self-explaining. It is good for teamwork and maintenance.

* Handling execution output or exceptions with Python is easier than shell script. Tons of Python packages are handy for you.

.. _h2d26691e27521b3852031565351c67:

More
====

* \ |LINK2|\ 

* \ |LINK3|\ 

.. bottom of content


.. |LINK1| raw:: html

    <a href="https://www.paramiko.org/" target="_blank">paramiko</a>

.. |LINK2| raw:: html

    <a href="https://iapyeh.github.io/sshscript/index" target="_blank">Documents</a>

.. |LINK3| raw:: html

    <a href="https://iapyeh.github.io/sshscript/examples/index" target="_blank">Examples</a>

