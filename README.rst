    
SSHScript
#########
System automation is the process of repeating network and execution operations to achieve desired results. SSHScript is a Python library that makes it easy to create system automation processes. It provides a simple and intuitive interface for executing commands on local and remote hosts, without requiring any knowledge of the subprocess module or Paramiko (SSH).

SSHScript is technically an integration of the subprocess and Paramiko modules, but it presents an unified interface that is more convenient and expressive for system automation tasks. It is also pure Python, which means that SSHScript scripts can be easily integrated with other Python libraries and tools.

Here is an example of a simple script in SSHScript syntax:

.. code-block:: python
    :linenos:

    ## filename: example.spy
    ## run: sshscript example.spy
    stdout, stderr, exitcode = $ls -l
    with $.connect('user@host', 'password):
        stdout, stderr, exitcode = $ls -l


Here is an example of a simple script with SSHScript module:

.. code-block:: python
    :linenos:

    ## filename: example.py
    ## run: python3 example.py
    import sshscript
    # Connect to a remote host
    from sshscript import SSHScriptSession
    session = SSHScriptSession()
    # Execute a command on the local host
    stdout, stderr, exitcode = session.exec_command('ls -l')
    remote_session = session.connect('user@host', 'password)
    # Execute a command on the remote host
    stdout, stderr, exitcode = remote_session.exec_command('ls -l')
    # Print the output of the command
    print(stdout)
    # Disconnect from the remote host
    remote_session.close()


Releases
========

The new experimental release is 2.0.2 (2023/10/6). There are lots of changes, but documentation is not available yet.

The last stable version is 1.1.17. (2022/9/22). Relase Notes_

More
====

* docs_

* Examples_


.. bottom of content

.. _paramiko : https://www.paramiko.org/

.. _docs : https://iapyeh.github.io/sshscript/index

.. _Examples : https://iapyeh.github.io/sshscript/examples/index


.. _Notes : https://iapyeh.github.io/sshscript/release-v1.1.17
