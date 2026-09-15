---
title: "Threading"
parent: "Advanced Session API"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
---

# Threading

SSHScript v3.1 does not replace the process-wide `threading.Thread` class.
Regular Python code should make Session ownership explicit. Transformed
`.spy` files additionally provide scoped Session inheritance for recognized
Thread constructors.

## Regular Python: own a Session per worker

Creating and closing the Session inside each worker makes lifetime and
failure boundaries clear:

```python
from concurrent.futures import ThreadPoolExecutor
from sshscript import Session


def remote_hostname(host):
    local = Session()
    try:
        with local.connect(host) as remote:
            stdout, stderr = remote.exec_command(
                "hostname",
                shell=False,
            )
            return host, str(stdout).strip()
    finally:
        local.close(strict=True)


hosts = [
    "ops@web-1.example.net",
    "ops@web-2.example.net",
]

with ThreadPoolExecutor(max_workers=len(hosts)) as pool:
    for host, hostname in pool.map(remote_hostname, hosts):
        print(host, hostname)
```

Each worker verifies host keys and authenticates independently. Futures also
return worker exceptions to the main thread when results are consumed.

When workers need a shared input value, pass it as a normal function
argument. Do not rely on an implicit global Session in an ordinary `.py`
module.

## `.spy` files: scoped Session inheritance

The `.spy` source transformer recognizes `threading.Thread(...)` and imported
`Thread(...)` constructors. It creates a standard Thread that snapshots the
active SSHScript Session stack when the Thread is constructed, installs that
stack only while the target runs, and clears it afterward.

```python
import threading


def check_host():
    $hostname
    print($.stdout.strip())


with $.connect("ops@example.net"):
    worker = threading.Thread(target=check_host)
    worker.start()
    worker.join()
```

The worker therefore sees the connected Session that was active at
construction time. This behavior belongs to transformed `.spy` code only; it
does not monkey-patch other libraries or ordinary Python threads.

## Collect failures

An exception printed by a raw worker Thread does not automatically become an
exception in the caller. Store worker results and errors, use
`concurrent.futures`, or explicitly raise collected failures after
`join()`. A test must not pass merely because an assertion failed in a
background Thread.

The credentialed `language.spy` threaded mode follows this rule by collecting
worker failures and raising them in the main thread.

## Test without SSH credentials

The credential-free test suite verifies connected Session inheritance with
in-memory SSH clients:

```sh
python3 -m unittest discover -v -s unittest -p 'test_*.py'
```

See [Development and Testing](../development-and-testing) for the complete
release gate and the separate manual integration modes.

Last Updated: 2026-09-14 18:02:02
