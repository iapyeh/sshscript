    
SSHScript
#########
System automation is the process of automating repetitive tasks by executing commands on local and remote hosts. SSHScript is a Python library that makes system automation easy. It provides a simple and intuitive interface for executing commands, without requiring any knowledge of the subprocess module or Paramiko (SSH).

Benefits of SSHScript
=====================
* Unified interface: SSHScript integrates the subprocess and Paramiko modules into a single, unified interface that is more convenient and expressive for system automation tasks.
* Pure Python: SSHScript scripts are pure Python, which means that they can be easily integrated with other Python libraries and tools.
* Easy to use: SSHScript is easy to use, even for those with limited programming experience.

Examples
========

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
