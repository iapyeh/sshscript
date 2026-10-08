# Console authentication tests

These tests cover the unreleased su/sudo handshake and failure recovery. Run
them from the source directory with SSHScript's runtime dependencies installed:

```sh
python3 -m unittest discover -v -s unittest -p 'test_console_authentication.py'
python3 -O -m unittest discover -v -s unittest -p 'test_console_authentication.py'
```

The suite uses real local Bash, PTY/pipe channels, and a simulated authentication
program. It does not call real su/sudo or need root privileges, account passwords,
SSH credentials, or a network connection. A temporary fixture records only the
number of password inputs. Available sh, zsh, csh, and tcsh executables also
exercise bootstrap quoting, including sudo's documented `-i` argv rebuilding.

Coverage includes:

- password and passwordless entry with PTYs and pipes;
- delayed success and rejection after more than two seconds;
- fragmented password prompts, banners, and terminal command echo;
- a second password prompt without sending a second password;
- policy denial and a target shell exiting after the authentication marker;
- shared entry deadlines, including `initials`, and bounded failure recovery;
- refusal of further commands after unconfirmed pipe-channel recovery;
- Session factories with `shell=False`, nested entry, and custom templates;
- manual target-shell exit without a second exit being sent to the parent;
- lock, thread-stack, and implicit-parent cleanup after failure; and
- single-use contexts and capability-dependent command construction.

Run all existing gates with:

```sh
python3 tools/run_checks.py
```

## Native-system validation before release

The simulated tests establish protocol behavior. They do not validate an actual
utility's authentication, PAM stack, account startup files, sudoers rules, or
signal handling. The following matrix still requires native-system checks:

| Environment | What to verify |
| --- | --- |
| Linux with modern util-linux su | Cached `--pty` capability and the resulting su PTY proxy |
| Linux with older util-linux or BusyBox su | Operation without `--pty`, password prompts, and `-c` placement |
| FreeBSD | `-c` after USER as a target-shell argument, csh/tcsh login shell, and Bash found through PATH |
| macOS | BSD su behavior, PTY line handling, sudo login-shell argument reconstruction |
| Local subprocess and SSH channel on each environment | Stdout/stderr routing, readiness, interruption, and recovery |

Use the [manual interactive examples](../API_GUIDE.md#interactive-usage) on an
existing account permitted by that host's policy. For sudo, verify root and,
where permitted, a non-root target through the retained sudo-to-su route.
Exercise `login=True/False`, `get_pty=True/False`, and `shell=True/False` for
combinations the utility and policy support. Rejection of an unsupported
combination is acceptable; entering the block as the original account is not.

Verify successful entry with `id -u` inside the block. For an intentionally
incorrect password, verify that the block body is not entered and the password
is sent once. After a nested failure, check whether a parent command succeeds
under the original UID; if recovery is unconfirmed, that command must instead
raise the channel's stored failure. An unresolved timeout must never count as
successful authentication. Create a fresh context for an intentional retry.

Record OS and utility versions, target login-shell family, the cached
`session.console_info`, chosen API options, resulting exception, and recovery
outcome. Keep real passwords and private host details out of tracked fixtures.
The current `console_info` cache supplies `is_su_pty_ok`, not a populated
OS/distribution inventory; use capability probes as the primary decision input.

## Native evidence and support boundary

SSHScript aims to let engineers and AI reliably execute, understand, and hand
off automation. For privilege changes, success means a verified target UID and
shell readiness. A failure must not enter the body. Continuing under the parent
requires a confirmed original UID/PID; otherwise the channel must reject work.
A timeout is unresolved execution, never successful authentication or proof that
a password was wrong. Host authorization remains the application's responsibility.

`test_native_console_authentication.py` runs actual su/sudo, PAM and sudoers;
it is opt-in and skipped during ordinary discovery. `tools/run_native_auth_ci.py`
uses the candidate wheel in a new venv, first as the disposable non-root login
account through local subprocesses, then through real loopback OpenSSH. It tests
successful su/root-sudo across login, PTY/pipe and direct/base-shell options,
nested target UID and parent PID restoration, wrong/missing passwords, actual
sudoers denial, passwordless sudo, and deadlines during authenticated setup.
Unconfirmed failure recovery is acceptable only when subsequent commands are
rejected; silent continuation with a different identity is a test failure.

On a disposable Ubuntu host with passwordless administrative sudo:

```sh
python tools/check_release.py --output /tmp/native-auth-wheel
bash tools/setup_openssh_ci.sh /tmp/native-auth.env
set -a
. /tmp/native-auth.env
set +a
python tools/run_native_auth_ci.py --wheel /tmp/native-auth-wheel/*.whl \
  --report /tmp/native-auth-report.json
```

The setup creates throwaway accounts and a sudoers file. Use a fresh VM or CI
runner, never a daily workstation; destroy that VM after a manual run. The CI
workflow removes the fixture accounts, sudoers entry and SSH server. The
configuration contains disposable passwords: keep the environment file private
and delete it with the fixture. The test runner passes passwords over stdin,
never command-line arguments, and the JSON report excludes them.

CI and the release OpenSSH gate require both backends to pass without skipped
native cases. Each Python 3.11/3.14 job saves a JSON report with OS, Python,
package/tool versions and observed recovery outcomes. A configured workflow is
not evidence of a successful run: review the candidate's actual reports before
calling native authentication validated.

Current scope: this gate targets Ubuntu's util-linux su, sudo and PAM with Bash.
macOS, FreeBSD, BusyBox/older util-linux, other login shells and site-specific PAM
or sudo policies remain unverified until corresponding native reports exist.
The generic Python/macOS unit job does not validate native macOS authentication.
Real password input counts remain covered by the simulated protocol fixture;
these native tests do not instrument PAM to claim passwords were sent once.
