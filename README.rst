
SSHScript
#########

You can take the SSHScript as an automation tool in Python. Functionally, the SSHScript is something like the Ansible. Instead of writing descriptive YML files, just write Python scripts with the simplicity of Python and the power of all Python packages. 

Technically, the SSHScript is an integration of subprocess and Paramiko_ . It provides an unique interface to invoke commands locally and remotely. Something like embedding shell commands in a python script. 

For example:


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


Why and Features
================

The idea is that many automation tasks are running commands and dealing with outputs on localhost and remote hosts. Between these scripts, there are many common routines. Eg. making ssh connections, execution and collecting data. That's where the SSHScript comes into play. The most charming part is that you could directly process the resulting data in Python. It then enables you to efficiently build complex data structure and working flow with object-oriented approach.


* Easy to use, quick to learn. you can utilize the power of subprocess and Paramiko to execute commands and make ssh connections even having no idea of both.

* Embedding shell commands in Python scripts are intuitive and self-explaining. It is good for teamwork and maintenance.

* Handling execution output or exceptions with Python is easier than shell script. Tons of Python packages are handy for you.

* With thread support.


More
====

* docs_

* Examples_


* `Release Notes`_


.. bottom of content


.. bottom of content

.. _Paramiko : https://www.paramiko.org/

.. _docs : https://iapyeh.github.io/sshscript/index

.. _Examples : https://iapyeh.github.io/sshscript/examples/index


.. _`Release Notes` : https://iapyeh.github.io/sshscript/releasenotes

