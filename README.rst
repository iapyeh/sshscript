    
SSHScript
#########

System automation is the process of automating repetitive tasks by executing commands on local and remote hosts.

SSHScript is a Python library that provides a simple and intuitive way to automate common tasks that involve running commands and dealing with outputs on local and remote hosts, without requiring any knowledge of the subprocess module or Paramiko (SSH).

SSHScript makes it easy to write scripts that can connect to remote hosts via SSH and execute commands, and it allows you to process the resulting data directly in Python. This enables you to build complex data structures and processing flows using an object-oriented approach. Parallel execution support: SSHScript supports parallel execution of commands using threads.

|pic2|

.. |pic2| image:: https://iapyeh.github.io/sshscript/v2/methodology.png
          :alt: my-picture2

Example Codes
=============

An example of SSHScript dollar-syntax (v2.0):

.. code-block:: python

    ## filename: example.spy
    ## run: sshscript example.spy
    $hostname
    ## get output by $.stdout, $.stderr and $.exitcode
    print('localhost name is ', $.stdout.strip())
    ## get an interactive sudo console of locahost
    with $.sudo('password') as sudoconsole:
        sudoconsole('whoami')
        assert 'root' in sudoconsole.stdout
        sudoconsole('ls -l $HOME')

    ## connect to a remote host by ssh
    with $.connect('user1@host', 'password'):
        $hostname
        ## get output by $.stdout, $.stderr and $.exitcode
        print('remote name is ', $.stdout.strip())
        ## get an interactive sudo console of the remote host
        with $.sudo('password') as sudoconsole:
            sudoconsole('whoami')
            assert 'root' in sudoconsole.stdout
            sudoconsole('ls -l $HOME')
        ## connect to nested remote host
        with $.connect('user2@nestedhost', pkey=$.pkey('/home/user1/.ssh/id_rsa')):
            $hostname
            ## get output by $.stdout, $.stderr and $.exitcode
            print('nested remote name is ', $.stdout.strip())
            ## get an interactive sudo console of the nested remote host
            with $.sudo('password') as sudoconsole:
                sudoconsole('whoami')
                assert 'root' in sudoconsole.stdout
                sudoconsole('ls -l $HOME')


An example of SSHScript module(v2.0):

.. code-block:: python

    ## filename: example.py
    ## run: python3 example.py
    import sshscript
    from sshscript import SSHScriptSession
    session = SSHScriptSession()
    # Execute commands on localhost
    session('df')
    for line in session.stdout.split('\n'):
        cols = line.split()
        if len(cols)>5: print(f'ussage of {cols[0]} is {cols[4]}')
    ## connect to remote by ssh
    with session.connect('user1@host', 'password') as remote_session:
        # Execute commands on the remote host
        remote_session('df')
        for line in remote_session.stdout.split('\n'):
            cols = line.split()
            if len(cols)>5: print(f'ussage of {cols[0]} is {cols[4]}')
        with remote_session.connect('user2@nestedhost', pkey=remote_session.pkey('/home/user1/.ssh/id_rsa') as nested_remote_session:
            # Execute commands on the nested remote host
            nested_remote_session('df')
            for line in nested_remote_session.stdout.split('\n'):
                cols = line.split()
                if len(cols)>5: print(f'ussage of {cols[0]} is {cols[4]}')

Benefits of using SSHScript
============================

* Easy to use: SSHScript is easy to use, even for those with limited programming experience. It abstracts away the complexity of the subprocess and Paramiko modules, so you can focus on writing your scripts.

* Intuitive and self-explanatory: SSHScript uses a simple and intuitive syntax, making it easy to read and write your scripts. You can embed shell commands directly in your Python scripts, which makes your scripts more readable and self-explanatory.

* Unified interface: SSHScript provides an unified interface for interacting with both local and remote hosts. This makes it easy to write scripts that can be used to automate tasks on any type of host.

* Easier handling of outputs and exceptions: SSHScript makes it easy to handle the output and exceptions of your scripts. You can use Python's built-in data structures and exception handling mechanisms to write more robust and maintainable scripts.

* Pure Python: SSHScript is written in pure Python, which means that it can be easily integrated with other Python libraries and tools. This makes it easy to extend SSHScript with new features and functionality.

* Leverage the Python ecosystem: SSHScript scripts are pure Python, which means that they can leverage the vast ecosystem of Python packages. This gives you access to a wide range of tools and libraries for tasks such as data processing, machine learning, and web development.

Use cases
==========

SSHScript can be used for a variety of tasks, including:

- Provisioning and configuration: SSHScript can be used to automate the provisioning and configuration of servers, networks, and other devices.

- Data collection and processing: SSHScript can be used to collect data from remote hosts and process it in Python. This can be useful for tasks such as monitoring, logging, and reporting.

- Deployment and testing: SSHScript can be used to deploy and test software on remote hosts.

- Troubleshooting and maintenance: SSHScript can be used to troubleshoot and maintain remote systems.

- Overall, SSHScript is a powerful and flexible tool that can be used to automate a wide range of common SSH tasks. It is easy to use and learn, and it provides a number of benefits over traditional shell scripting.

SSHScript can be used to automate a wide variety of system tasks, such as:

* Deploying and configuring servers
* Managing backups and restores
* Monitoring and troubleshooting systems
* Automating repetitive tasks

SSHScript is a powerful tool for system automation, and it is easy to use, even for those with limited programming experience.

New Releases
============

The new experimental release is 2.0.2 (2023/10/17). There are lots of changes.

* `SSHScript V2.0 Reference Guide`_

SSHScript v1.0
==============

* `SSHScript V1.0 Reference Guide`_

* `SSHScript V1.0 Examples`_


.. bottom of content

.. _paramiko : https://www.paramiko.org/

.. _`SSHScript V2.0 Reference Guide` : https://iapyeh.github.io/sshscript/v2/index

.. _`SSHScript V1.0 Reference Guide` : https://iapyeh.github.io/sshscript/v1/index

.. _`SSHScript V1.0 Examples` : https://iapyeh.github.io/sshscript/v1/examples/index


[![Downloads](https://pepy.tech/badge/sshscript)](https://pepy.tech/project/sshscript)

|ImageLink|_

.. |ImageLink| image:: https://pepy.tech/badge/sshscript
.. _ImageLink: https://pepy.tech/project/sshscript