# Completed console results and continuous programs

Run from the `working_branch` checkout with its declared dependencies installed:

```sh
python3 -m unittest discover -s unittest -p test_console_results.py -v
python3 -m unittest discover -s unittest -p test_recommended_examples.py -v
python3 tools/run_checks.py
```

These credential-free tests cover single-dollar and persistent-shell three-value
results, retained text snapshots, pipe stderr completion, check failures with a
saved result, unchanged interactive input dispatch, and a continuous local Python
process stopped via both enter()/Ctrl-C and a managed job's stop(). Canonical
runnable API guide examples execute as part of the normal suite.

No capture privileges, tcpdump installation, external SSH host, or credentials
are required. The continuous Python process exercises lifecycle behavior; this
is not evidence of real tcpdump or remote OpenSSH capture behavior. Remote
protocol tests and opt-in OpenSSH integration tests are separate.

The console result change is unreleased. Published 3.1.5 console commands still
return two buffers. For new source consumers, prefer `result = console(command)`
and named fields, or unpack exactly stdout, stderr, exitcode. Read API_GUIDE.md
for finite capture, streaming with a stop condition and fallback deadline, and
capture inside a shell/privilege context.

## Console foreground jobs

Run `python3 -m unittest discover -s unittest -p test_console_job.py -v` and
repeat with `python3 -O`. Coverage includes PTY/pipe completion and stderr
fences, bounded capture/stream overflow, deadline/stop/recovery, exclusive use,
creator-thread enforcement, `.spy` scope, preserved shell state, simulated
su/sudo UID/PID protocol and a real Paramiko pipe-console fixture. Native
su/sudo job identity and PTY stop are opt-in cases in
`test_native_console_authentication.py`; they require the disposable CI fixture.
These tests do not establish real tcpdump or every OS/PAM/sudo policy behavior.
