"""Credential-free console protocol tests using real shells and simulated auth.

These exercise PTY/pipe I/O without sudo privileges or a real account password.
OS command layout checks supplement, rather than replace, real Linux/BSD tests.
"""
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from channelutils import SuConsole, SudoConsole, _AuthCommand, _auth_bootstrap, _validate_enter_timeout
from session import Session


AUTH_FIXTURE = r'''
import os, signal, sys, time
mode, delay, countfile = sys.argv[1:4]
delay = float(delay)
signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
if mode == "banner":
    sys.stderr.write("Please change your password; sorry for the downtime.\n")
    sys.stderr.flush()
if mode not in ("nopassword", "banner"):
    if mode == "fragment":
        sys.stderr.write("pass")
        sys.stderr.flush()
        time.sleep(0.05)
        sys.stderr.write("word: ")
    else:
        sys.stderr.write("password: ")
    sys.stderr.flush()
    value = sys.stdin.readline()
    with open(countfile, "a") as count:
        count.write("input\n")
    time.sleep(delay)
    if mode == "retry":
        sys.stderr.write("\npassword: ")
        sys.stderr.flush()
        sys.stdin.readline()
        with open(countfile, "a") as count:
            count.write("input\n")
        sys.exit(1)
    if mode == "reject":
        sys.stderr.write("\nsu: Authentication failure\n")
        sys.stderr.flush()
        sys.exit(1)
    if mode == "hang":
        time.sleep(30)
        sys.exit(1)
    if mode == "policy":
        sys.stderr.write("\nsudo: user is not allowed to run this command\n")
        sys.stderr.flush()
        sys.exit(1)
else:
    time.sleep(delay)
os.execvp(sys.argv[4], sys.argv[4:])
'''


class ConsoleCommandTests(unittest.TestCase):
    def test_su_capabilities_not_distribution_names_select_pty(self):
        for os_name, supports_pty in [("linux", True), ("linux", False),
                                      ("freebsd", False), ("darwin", False)]:
            session = SimpleNamespace(connected=False, os_name=os_name,
                                      is_su_pty_ok=supports_pty)
            command = SuConsole.get_command(session, "target", True, True)
            argv = shlex.split(command)
            self.assertEqual("--pty" in argv, supports_pty)
            # On BSD this -c must be a target-shell argument, not a login class.
            self.assertGreater(argv.index("-c"), argv.index("target"))
            self.assertNotIn("--login", argv)
            self.assertNotIn("/bin/bash", command)

    def test_sudo_retains_su_policy_and_login_modes(self):
        session = SimpleNamespace(connected=True)
        for login in (True, False):
            root = shlex.split(SudoConsole.get_command(session, None, login))
            self.assertEqual("-i" in root, login)
            self.assertIn("-S", root)
            self.assertEqual(root[root.index("-p") + 1], "password: ")
            target = shlex.split(SudoConsole.get_command(session, "target", login))
            self.assertIn("su", target)
            self.assertNotIn("-u", target)
            self.assertGreater(target.index("-c"), target.index("target"))

    def test_bootstrap_works_through_bourne_and_csh_login_shells(self):
        username = pwd.getpwuid(os.getuid()).pw_name
        command = _auth_bootstrap(username, False, "testtoken")
        self.assertNotIn("__SS_AUTH_testtoken__", command)
        self.assertNotIn("$", command)
        # sudo -i rebuilds a shell command from argv, leaving dollars unescaped.
        sudo_i = " ".join("".join(c if c.isalnum() or c in "_-$" else "\\" + c
                                 for c in arg) for arg in shlex.split(command))
        for name in ("bash", "sh", "zsh", "csh", "tcsh"):
            executable = shutil.which(name)
            if not executable:
                continue
            for payload in (command, sudo_i):
                with self.subTest(shell=name, sudo_i=payload == sudo_i):
                    result = subprocess.run([executable, "-c", payload],
                        input='printf "PID=%s\\n" "$$"\nexit\n', text=True,
                        capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    match = re.search(r"__SS_AUTH_testtoken__:(\d+):(\d+)\n", result.stdout)
                    self.assertIsNotNone(match, result.stdout)
                    self.assertEqual(int(match[1]), os.getuid())
                    self.assertIn("PID=" + match[2], result.stdout)

    def test_invalid_timeout_rejected(self):
        for value in (0, -1, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _validate_enter_timeout(value)
        for value in (True, None, "10"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                _validate_enter_timeout(value)


@unittest.skipUnless(shutil.which("bash"), "Bash is required for console contexts")
class ConsoleAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sshscript-auth-")
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Path(self.tmp.name) / "auth.py"
        self.fixture.write_text(AUTH_FIXTURE)
        self.count = Path(self.tmp.name) / "count"
        self.username = pwd.getpwuid(os.getuid()).pw_name
        self.session = Session()
        self.addCleanup(self.session.close)

    def console(self, parent, mode="success", delay=0, timeout=5, initials=None):
        command = shlex.join([sys.executable, str(self.fixture), mode,
                              str(delay), str(self.count)]) + " {auth_command}"
        return SudoConsole(parent, "test-only", username=self.username,
                           command=command, login=False, enter_timeout=timeout,
                           initials=initials)

    def test_password_and_passwordless_entry_with_pty_and_pipes(self):
        for pty in (True, False):
            with self.subTest(pty=pty), self.session.shell(get_pty=pty) as parent:
                for mode in ("success", "nopassword"):
                    with self.subTest(mode=mode), self.console(parent, mode) as target:
                        stdout, _, exitcode = target("id -u")
                        self.assertIn(str(os.getuid()), str(stdout))
                    stdout, _, exitcode = parent("printf parent-alive")
                    self.assertIn("parent-alive", str(stdout))

    def test_delayed_success_is_not_assumed_after_two_seconds(self):
        with self.session.shell() as parent:
            start = time.monotonic()
            with self.console(parent, delay=2.2) as target:
                self.assertGreaterEqual(time.monotonic() - start, 2.2)
                self.assertIsNotNone(target.channel.prompt)
            self.assertEqual(self.count.read_text().splitlines(), ["input"])

    def test_delayed_rejection_restores_parent_without_retry(self):
        with self.session.shell() as parent:
            before = parent.channel.layer_count
            with self.assertRaises(PermissionError):
                self.console(parent, mode="reject", delay=2.2).__enter__()
            self.assertEqual(self.count.read_text().splitlines(), ["input"])
            self.assertEqual(parent.channel.layer_count, before)
            self.assertFalse(parent.channel.executing_lock.locked())
            stdout, _, exitcode = parent("printf recovered")
            self.assertIn("recovered", str(stdout))

    def test_second_password_prompt_does_not_send_password_again(self):
        with self.session.shell() as parent:
            with self.assertRaises(PermissionError):
                self.console(parent, mode="retry").__enter__()
            self.assertEqual(self.count.read_text().splitlines(), ["input"])
            self.assertFalse(parent.channel.executing_lock.locked())
            stdout, _, exitcode = parent("printf recovered")
            self.assertIn("recovered", str(stdout))

    def test_timeout_is_not_success_and_interrupt_restores_pty_parent(self):
        with self.session.shell() as parent:
            with self.assertRaises(TimeoutError):
                self.console(parent, mode="hang", timeout=0.3).__enter__()
            self.assertFalse(parent.channel.executing_lock.locked())
            stdout, _, exitcode = parent("printf recovered")
            self.assertIn("recovered", str(stdout))

    def test_initials_run_after_readiness(self):
        with self.session.shell() as parent:
            with self.console(parent, initials=["export SS_TEST_READY=yes"]) as target:
                stdout, _, exitcode = target('printf "%s" "$SS_TEST_READY"')
                self.assertIn("yes", str(stdout))

    def test_plain_custom_command_is_rejected_before_sending(self):
        with self.session.shell() as parent:
            with self.assertRaisesRegex(ValueError, "auth_command"):
                SudoConsole(parent, command="sudo bash")
            stdout, _, exitcode = parent("printf parent-alive")
            self.assertIn("parent-alive", str(stdout))

    def test_fragmented_prompt_and_banner_words_are_not_false_success_or_failure(self):
        with self.session.shell() as parent:
            for mode in ("fragment", "banner"):
                with self.subTest(mode=mode), self.console(parent, mode=mode) as target:
                    stdout, _, exitcode = target("printf ready")
                    self.assertIn("ready", str(stdout))

    def test_command_echo_is_not_an_authentication_marker(self):
        with self.session.shell() as parent:
            parent("stty echo")
            start = time.monotonic()
            with self.console(parent, mode="nopassword", delay=0.2):
                self.assertGreaterEqual(time.monotonic() - start, 0.2)

    def test_policy_exit_is_not_reported_as_bad_password(self):
        with self.session.shell() as parent:
            with self.assertRaisesRegex(RuntimeError, "exited before readiness"):
                self.console(parent, mode="policy").__enter__()
            stdout, _, exitcode = parent("printf recovered")
            self.assertIn("recovered", str(stdout))

    def test_initials_share_the_authentication_deadline(self):
        with self.session.shell() as parent:
            with self.assertRaises(TimeoutError):
                self.console(parent, delay=0.1, timeout=0.3,
                             initials=["sleep 0.4"]).__enter__()
            stdout, _, exitcode = parent("printf recovered")
            self.assertIn("recovered", str(stdout))

    def test_unconfirmed_pipe_recovery_blocks_further_commands(self):
        with self.session.shell(get_pty=False) as parent:
            with self.assertRaises(TimeoutError):
                self.console(parent, mode="hang", timeout=0.3).__enter__()
            self.assertFalse(parent.channel.executing_lock.locked())
            with self.assertRaisesRegex(RuntimeError, "recovery is unconfirmed"):
                parent("printf must-not-run")

    def test_shell_exiting_after_auth_does_not_enter_body_as_parent(self):
        with self.session.shell() as parent:
            token = "deadtarget"
            script = ('printf "\\n%s%s:%s:%s\\n" "__SS_AUTH_" '
                      + shlex.quote(token + "__") + ' "$(id -u)" "$$"; exit 127')
            command = _AuthCommand(shlex.join(["bash", "-c", script]), token)
            console = SudoConsole(parent, username=self.username,
                                  command=command, enter_timeout=2)
            with self.assertRaises(RuntimeError):
                console.__enter__()
            stdout, _, exitcode = parent("printf recovered")
            self.assertIn("recovered", str(stdout))

    def test_direct_session_factory_preserves_token_and_timeout(self):
        def generated(*args):
            token = "directtoken"
            command = shlex.join([sys.executable, str(self.fixture), "success",
                                  "0", str(self.count)])
            return _AuthCommand(command + " " + _auth_bootstrap(self.username, False, token), token)
        for method, cls in (("su", SuConsole), ("sudo", SudoConsole)):
            for pty in (True, False):
                with self.subTest(method=method, pty=pty):
                    with patch.object(cls, "get_command", side_effect=generated):
                        factory = getattr(self.session, method)
                        with factory(username=self.username, password="test-only",
                                     shell=False, get_pty=pty, login=False,
                                     enter_timeout=2) as target:
                            stdout, _, exitcode = target("id -u")
                            self.assertIn(str(os.getuid()), str(stdout))

    def test_manual_exit_does_not_exit_parent_a_second_time(self):
        with self.session.shell() as parent:
            context = self.console(parent, mode="nopassword")
            with context as target:
                target.send("exit\n")
                target.expect(context._line("RETURN", r":(\d+)"), timeout=2)
            stdout, _, exitcode = parent("printf parent-alive")
            self.assertIn("parent-alive", str(stdout))

    def test_factory_entry_failure_restores_stack_and_closes_implicit_parent(self):
        import patching
        before = list(patching.get_thread_stack())
        token = "factoryfailure"
        command = shlex.join([sys.executable, str(self.fixture), "reject",
                              "0", str(self.count)])
        command = _AuthCommand(command + " " + _auth_bootstrap(self.username, False, token), token)
        for shell in (True, False):
            with self.subTest(shell=shell), patch.object(SudoConsole, "get_command", return_value=command):
                context = self.session.sudo(password="test-only", username=self.username,
                                            shell=shell, enter_timeout=2)
                with self.assertRaises(PermissionError):
                    context.__enter__()
                self.assertEqual(context.enter_count, 0)
                self.assertEqual(list(patching.get_thread_stack()), before)
                self.assertTrue(context.channel.closed)

    def test_context_is_single_use(self):
        with self.session.shell() as parent:
            context = self.console(parent, mode="nopassword")
            with context:
                pass
            with self.assertRaisesRegex(RuntimeError, "single-use"):
                context.__enter__()
