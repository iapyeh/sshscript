<div style="text-align:right"><a href="./index">Index</a></div>

# SSHScript v2.0.2 Release Notes (on working)


## Summary

SSHScript v2.0.2 reimplements its dollar-syntax functionality using the Python.ast module, making it more flexible and consistent. You can now use all SSHScript functions in a regular Python script without needing to use dollar-syntax. Multi-threading support has also been refined, allowing you to connect to multiple hosts in multiple threads.

### New Features

- $.sudo() to get root console

- $.su() to get another user console.

- $.enter() to get an interactive console of interactive commands(eg. mysql-client).

- $.iterate()  to iterate outputs from foreground commands like "tcpdump".

- $.thread() to create a new SSHScript-aware thread in a multi-threading environment.

### Simplifications 

- The usage case of with-dollar is now limited to invoking shell only.

- The syntax @{var} is removed from one-dollar commands (e.g., $hostname) since $f-string is now supported.

## Additional Notes

- This release is still under development, but all features should be working as expected.

- If you find any bugs or have any suggestions, please report them on the SSHScript GitHub repository.

