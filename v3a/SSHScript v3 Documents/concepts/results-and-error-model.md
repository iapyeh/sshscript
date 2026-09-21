---
title: "Results and Error Model"
parent: "Concepts"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 3
permalink: /v3a/concepts/results-and-error-model/
---

# Results and Error Model

A completed command, an API failure, and cleanup failure are different outcomes.

## Command results

Command calls return live stdout/stderr buffers. Use `str(stdout)` to take a
stable text snapshot. A nonzero exitcode remains result data unless local
`check=True` requests an exception. Remote callers should inspect exitcode
explicitly. A successful API call does not imply command success.

## Exceptions

Wrong types raise TypeError; invalid values raise ValueError. Invalid lifecycle
transitions raise RuntimeError. Closed operations raise BrokenPipeError, ended
waits raise EOFError, and timeouts raise TimeoutError. Disconnected SFTP access
raises SSHScriptException. Original filesystem and Paramiko errors propagate.
The complete matrix is in [Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

Runtime validation remains active under `python -O`. User assertions are
removed by optimized Python; production scripts must use explicit result
checks. AssertionError was never a supported package validation contract.

## Cleanup and transfers

Transfers return paths and do not update command exitcode. Cleanup reports
failures through `close_errors` and the bool returned by `close()`;
`close(strict=True)` raises after cleanup. Preserve the primary operation
exception when reporting a cleanup failure. High-level automatic cleanup does
not replace an application's explicit cleanup reporting policy.

See [Failure Model and Production Checklist](../../security-and-operations/failure-model-and-production-checklist/)
for production handling patterns.

Last Updated: 2026-09-21 17:45:03
