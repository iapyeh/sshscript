<<<<<<< HEAD
=======


Announcement
############

v1.1.16 has released on 2022/9/5. Users are recommanded to upgrade by 

.. code::

    pip3 install --upgrade sshscript


+---------------------------------------------------------------------------------------------------+
|For installers of version v1.101, v1.102 and v1.103.  Please do upgrade with                       |
+---------------------------------------------------------------------------------------------------+
.. code:: 

    python3 -m pip install sshscript==1.1.16
    
Please see v1.1.16 Relaese Notes_ for details.
>>>>>>> b66cb1cea37129ca31d9b0d33620ebcbc40ec793
    
SSHScript
#########
System automation is a process of realizing management logics by repeating networking and execution. SSHScript makes Python an easy tool for creating system automation processes. With syntax sugar of SSHScript, writing python scripts to execute commands on local host or remote hosts is easy.

You just need to embed commands and networking in python scripts. SSHScript would execute them and let you handle outputs all in Python. You need not know programming about the subprocess module and Paramiko(ssh).

Technically, SSHScript is an integration of the subprocess and Paramiko. It provides an unique interface to invoke commands on local host and remote hosts. It could perform the same functionality as a shell script. But it is pure Python.

Releases
========

The last version is 1.1.16. (2022/9/5). Relase Notes_

More
====

* docs_

* Examples_


.. bottom of content

.. _paramiko : https://www.paramiko.org/

.. _docs : https://iapyeh.github.io/sshscript/index

.. _Examples : https://iapyeh.github.io/sshscript/examples/index


.. _Notes : https://iapyeh.github.io/sshscript/release-v1.1.16
