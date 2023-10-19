    
SSHScript
#########
System automation is the process of repeating network and execution operations to achieve desired results. SSHScript is a Python library that makes it easy to create system automation processes. It provides a simple and intuitive interface for executing commands on local and remote hosts, without requiring any knowledge of the subprocess module or Paramiko (SSH).

SSHScript is technically an integration of the subprocess and Paramiko modules, but it presents an unified interface that is more convenient and expressive for system automation tasks. It is also pure Python, which means that SSHScript scripts can be easily integrated with other Python libraries and tools.

Here is an example of a simple script in SSHScript syntax(v2):

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

    ## connect to remote by ssh
    with $.connect('user1@host', 'password):
        $hostname
        ## get output by $.stdout, $.stderr and $.exitcode
        print('remote name is ', $.stdout.strip())
        ## get an interactive sudo console of remote host
        with $.sudo('password') as sudoconsole:
            sudoconsole('whoami')
            assert 'root' in sudoconsole.stdout
            sudoconsole('ls -l $HOME')
        with $.connect('user2@nestedhost', pkey=$.pkey('/home/user1/.ssh/id_rsa')):
            $hostname
            ## get output by $.stdout, $.stderr and $.exitcode
            print('nested remote name is ', $.stdout.strip())
            ## get an interactive sudo console of remote host
            with $.sudo('password') as sudoconsole:
                sudoconsole('whoami')
                assert 'root' in sudoconsole.stdout
                sudoconsole('ls -l $HOME')


Here is an example of a simple script with SSHScript module(v2):

.. code-block:: python

    ## filename: example.py
    ## run: python3 example.py
    import sshscript
    from sshscript import SSHScriptSession
    session = SSHScriptSession()
    # Execute a command on the local host
    session('df')
    for line in session.stdout.split('\n'):
        cols = line.split()
        if len(cols)>5: print(f'ussage of {cols[0]} is {cols[4]}')
    ## connect to remote by ssh
    with session.connect('user1@host', 'password) as remote_session:
        # Execute a command on the remote host
        remote_session('df')
        for line in remote_session.stdout.split('\n'):
            cols = line.split()
            if len(cols)>5: print(f'ussage of {cols[0]} is {cols[4]}')
        with remote_session.connect('user2@nestedhost', pkey=remote_session.pkey('/home/user1/.ssh/id_rsa') as nested_remote_session:
            # Execute a command on the remote host
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
