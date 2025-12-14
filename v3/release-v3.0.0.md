# SSHScript v3.0.0 Release Notes

<div style="text-align:right;position:relative;top:-140px"><a href="./index">Back to Index</a></div>

## Summary

SSHScript v3.0.0 is a major release that focuses on simplifying the API, improving consistency, and enhancing the overall developer experience. This version introduces several breaking changes from v2.x to create a more powerful and intuitive scripting environment.

## 💥 Breaking Changes & Major Improvements

### 1. Unified Interactive Command with `$.enter()`

The `$.iterate()` method has been **removed**. The `$.enter()` method now provides the functionality of both `$.enter` and `$.iterate` from v2.

- **`$.enter()` now returns an iterable object.** You can loop directly over the `$.enter()` context manager to process streaming output from foreground commands like `tcpdump` or `tail -f`.
- This creates a single, consistent way to handle all types of interactive and long-running processes.

**v2.x (Old Way):**
```python
with $.iterate('tcpdump -vv') as loopable:
    for line in loopable:
        print(line)
```

**v3.0 (New Way):**
```python
with $.enter('tcpdump -vv') as stream:
    for line in stream:
        print(line)
```

### 2. Deprecated Syntax Removed

- **`@{var}` syntax is removed.** Python's f-strings are the standard and only way to format variables into commands.
  - **Removed:** `$echo @{my_var}`
  - **Correct:** `$f'echo {my_var}'`
- **Multi-line `with $"""..."""` is removed.** This syntax was confusing. Use `with $` or `with $#!/bin/bash` for opening a shell console.
  - **Removed:** `with $"""cd /tmp\nls -l"""`
  - **Correct:** `with $: $cd /tmp; $ls -l`

## ✨ New Features and Refinements

- **`$.include(path)`:** A new function to include another `.spy` script. This helps in organizing large projects by allowing you to reuse common functions and setups.
- **`console.clear()`:** A method on interactive console objects (from `$.enter`, `$.sudo`, etc.) to clear the internal `stdout` and `stderr` buffers. This is useful for getting only the output of the most recent command in a long interactive session.
- **Flexible `$.upload(src, [dst])`:** The `dst` argument in `$.upload()` is now optional. If omitted, it defaults to the basename of the `src` file.
- **`$.exit()`:** This function now behaves identically to `sys.exit()`, providing a consistent way to terminate a script.

## Bug Fixes

- Fixed an issue where `$.sudo()` could block indefinitely if an incorrect password was provided.
- Resolved an exception raised by `sys.exit()` when called from within a `.spy` file.