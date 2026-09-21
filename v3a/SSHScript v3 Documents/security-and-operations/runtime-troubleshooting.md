---
title: "Runtime Troubleshooting"
parent: "Security and Operations"
grand_parent: "SSHScript v3.1 Documentation"
nav_order: 4
permalink: /v3a/security-and-operations/runtime-troubleshooting/
---

# Runtime Troubleshooting

> **Documentation status: Placeholder**

This page will diagnose host-key rejection, authentication failure, connection
timeout, missing remote commands, shell quoting, unexpected exit status,
prompt mismatch, PTY behavior, SFTP permissions, thread failures, and cleanup
errors without exposing credentials.

Installation-specific problems remain documented in
[Installation Troubleshooting]({{ site.baseurl }}/v3a/SSHScript%20v3%20Documents/troubleshooting-installation/).

## Runtime validation under optimized Python

For argument failures, distinguish `TypeError` (wrong type) from `ValueError`
(invalid content). For channel failures, distinguish `RuntimeError` (invalid
lifecycle transition), `BrokenPipeError` (closed operation), `EOFError` (ended
while waiting), and `TimeoutError`. A disconnected SFTP request raises
`SSHScriptException`; reconnect before accessing SFTP. Do not catch
`AssertionError` as a package validation contract. These checks remain active
under `python -O`. See [Exceptions and Return Values]({{ site.baseurl }}/v3a/reference/exceptions-and-return-values/).

This section covers the production-hardening changes; the broader diagnostic
coverage described above is still planned.

Last Updated: 2026-09-21 17:45:03
