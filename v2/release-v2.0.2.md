<div style="text-align:right"><a href="./index">Index</a></div>

# SSHScript v2.0.2 Release Notes (Draft)


## Summary
SSHScript v2.0.2 reimplements its dollar-syntax functionality using the Python.ast module, making it more flexible and consistent. 
Threading support has also been reimplemented, and SSHScript v2.0.2 now supports connecting to multiple hosts at the same time.

You can also now use all SSHScript functions in a regular Python script without needing to use dollar-syntax. 
This makes your scripts easier to integrate with existing scripts.

## Improvements 

- Reimplemented syntax parsing: More flexible and consistent dollar-syntax functionality.
- Reimplemented threading support: SSHScript v2.0.2 now supports connecting to multiple hosts at the same time. This can improve the performance of your scripts, especially when you need to execute commands on multiple hosts simultaneously.
- Improved robustness and stability: SSHScript v2.0.2 has greatly refined the way it interacts with the shell console to improve its robustness and stability. This makes your scripts less likely to fail or crash.
- Handy functions for regular tasks: SSHScript v2.0.2 provides handy functions for regular tasks, such as sudo and su. This makes it easier to write scripts that perform these tasks.
- Better handling of foreground processes: SSHScript v2.0.2 now handles foreground processes, such as tcpdump, better. This makes it easier to write scripts that use these types of processes.

Overall, SSHScript v2.0.2 is a significant improvement over previous versions. It is more flexible, consistent, robust, and stable. It is also easier to use, thanks to the new handy functions and improved foreground process handling.

### New Features 

- `$.sudo(password)`, get a root console: The $.sudo function returns a console as the root user. This can be useful for executing commands that require root privileges.

- `$.su(username,password)`, get a different user console: The $.su() function returns a console as the specified user. This can be useful for executing commands as a different user, such as sudoer account.

- `$.enter(command)`, get an interactive console: The $.enter() function returns a console of an interactive process. This can be useful for executing interactive tools, such as `mysql-client`.

- `$.iterate(command)`, iterate over foreground command outputs: The $.iterate() function returns a loopable console for iterating over the output of a foreground command, such astcpdump`. This can be useful for processing the output of foreground commands in real time.

- `$.thread(target)`, create a new SSHScript-aware thread: The $.thread() function creates a new thread that takes the session as its effective sessions. This can be useful for executing commands in a multithreaded environment.


## Additional Notes

### Simplifications in the Roadmap of SSHScript v2.0

SSHScript v2.0 will focus on improving its simplicity. The following items are on the schedule and will be implemented in next releases:

- The usage case of with-dollar is now limited to invoking shell only. This means that with-dollar can no longer be used to execute commands. This is a simplification because it makes the with-dollar syntax more consistent and easier to understand.

    For example:
    ```
    ## would be invalid in the future
    with $"""
        #!/bin/bash
        cd $HOME
        """ as console:
            console('ls -l | grep ^d')

    ## valid in the future (this style is easier to understand)
    with $#!/bin/bash as console:
        console('cd $HOME')
        console('ls -l | grep ^d')
    ```

- The syntax @{var} will be removed from dollar-syntax, using $f-string is recommanded. This means that you should use Python f-strings instead of @{var} to insert variables into dollar-syntax commands. This is a simplification because f-strings are more concise and easier to use.

### Development of SSHScript v2.0 is in an early stage. If you find any bugs or have any suggestions, please post them on the `issues`.

Last updated on 2023-10-21

