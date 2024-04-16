    
SSHScript
#########
Many backend, DevOps and SRE engineers have daily tasks that involve repetitive manual operations between the Linux console and SSH. When automation is needed, shell scripts are often used. Have you ever thought about solving this with Python scripts?

SSHScript is a solution for those who have such an idea.The goal of SSHScript is to simply automate manual operations. Achieve the same functionality as shell scripts with Python.It can also use all Python packages and threading features.

To achieve the goal, it is necessary to simplify the functions of Python for SSH connections, executing CLI programs and shell commands, and changing the execution identity (sudo).SSHScript has achieved these things.

|pic2|

.. |pic2| image:: https://iapyeh.github.io/sshscript/v2/shellandsshscript.png
          :alt: my-picture2

Simple and Intuitive
====================
SSHScript adds dollar-syntax syntax sugar to Python, which allows you to write scripts that closely resemble the process of manually performing operations.
For example, here is a Python script with dollar-syntax that runs the hostname command on localhost, a remote server, and the server behind the remote server:

.. code-block:: 

    ## run "hostname" on localhost
    $hostname
    with $.connect('user@host1'):
        ## run "hostname" on host1
        $hostname 
        with $.connect('user@host2'):
                ## run "hostname" on host2, with is behind the host1
                $hostname


Flexible and Robust
=======================
SSHScript v2.0 makes a great improvement by providing all the features of dollar-syntax in the sshscript module. This makes SSHScript work exactly like any other counterpart package when integrating with existing projects. This allows users to use all of SSHScript's features in pure Python without writing dollar-syntax. 

Here is an example of the same script as above, but using only the sshscript module:

.. code-block::

    from sshscript import SSHScriptSession
    session = SSHScriptSession()
    ## run "hostname" on localhost
    session('hostname')
    with session.connect('user@host1') as host1_session:
        ## run "hostname" on host1
        host1_session('hostname')
        with host1_session.connect('user@host2') as host2_session:
                ## run "hostname" on host2, with is behind the host1
                host2_session('hostname')


Install
=======

.. code-block:: 

    $ pip3 install sshscript
    ## or
    $ python3 -m pip install sshscript


SSHScript depends on the Paramiko library. In some cases, it has been reported that an older version (1.1.17) of SSHScript was incorrectly installed. If you encounter this problem, the workaround is to manually install Paramiko and then reinstall SSHScript.

.. code-block::

    ## check version
    $ sshscript --version

    ## It should be 2.0 or higher. If it is older version, eg. 1.*. You can try to do the following steps:
    
    $ pip3 uninstall sshscript
    $ pip3 install paramiko
    $ pip3 install sshscript
    

Examples
=============

An example of SSHScript dollar-syntax (v2.0):

.. code-block:: 

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

.. code-block:: 

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

* `SSHScript v2.0 Reference Guide`_

SSHScript v1.0
==============

* `SSHScript v1.0 Reference Guide`_

* `SSHScript v1.0 Examples`_


.. bottom of content

.. _paramiko : https://www.paramiko.org/

.. _`SSHScript v2.0 Reference Guide` : https://iapyeh.github.io/sshscript/v2/index

.. _`SSHScript v1.0 Reference Guide` : https://iapyeh.github.io/sshscript/v1/index

.. _`SSHScript v1.0 Examples` : https://iapyeh.github.io/sshscript/v1/examples/index


|ImageLink|_

.. |ImageLink| image:: https://pepy.tech/badge/sshscript
.. _ImageLink: https://pepy.tech/project/sshscript
