"""Completed shell snapshots coexist with live interactive and managed output."""
from dataclasses import FrozenInstanceError
import shlex
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

from commandresult import CommandResult
from session import Session
from sessionwrapper import SessionWrapper
import sshscript


class ConsoleResultTests(unittest.TestCase):
    def local(self):
        session = Session()
        self.addCleanup(session.close)
        return session

    def test_shell_snapshot_status_and_failure(self):
        session = self.local()
        with session.shell('bash', get_pty=False) as shell:
            first = shell('printf first; printf error >&2; false')
            self.assertIsInstance(first, CommandResult)
            self.assertEqual(tuple(first), ('first', 'error', 1))
            self.assertEqual(first.command, 'printf first; printf error >&2; false')
            self.assertIsNone(first.host)
            self.assertGreaterEqual(first.duration, 0)
            shell('printf second', check=True)
            self.assertEqual(tuple(first), ('first', 'error', 1))
            with self.assertRaises(FrozenInstanceError):
                first.stdout = 'changed'
            with self.assertRaises(ValueError):
                stdout, stderr = first
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                shell('printf failed; false', check=True)
            self.assertEqual(tuple(caught.exception.result), ('failed', '', 1))
            self.assertEqual(caught.exception.stdout, 'failed')

    def test_pipe_stderr_is_fully_drained_before_snapshot(self):
        session = self.local()
        with session.shell('bash', get_pty=False) as shell:
            for index in range(8):
                result = shell("printf '_TT1_'; printf 'stderr-%s' " + str(index) + " >&2")
                self.assertEqual(tuple(result), ('_TT1_', 'stderr-' + str(index), 0))

    def test_dollar_result_in_and_outside_shell(self):
        namespace = sshscript.run_script(
            'first = $printf outside\n'
            'with $.shell("bash"):\n'
            '    second = $printf inside\n'
            '    stdout, stderr, status = $printf unpacked\n')
        self.assertEqual(tuple(namespace['first']), ('outside', '', 0))
        self.assertEqual(tuple(namespace['second']), ('inside', '', 0))
        self.assertEqual((namespace['stdout'], namespace['stderr'], namespace['status']),
                         ('unpacked', '', 0))

    def test_interactive_dispatch_retains_status_and_does_not_probe_exit(self):
        channel = Mock(hijacked=True)
        channel.owner.session.check = False
        channel.send_line.return_value = 'prompt'
        wrapper = SessionWrapper(Mock(channel=channel))
        self.assertEqual(wrapper('some input'), 'prompt')
        channel.send_line.assert_called_once_with('some input')
        channel.owner.session.get.assert_not_called()

    def test_enter_continuous_process_expect_ctrl_c_and_reuse_shell(self):
        session = self.local()
        script = "import time; print('capture-ready', flush=True); exec('while True: time.sleep(1)')"
        command = shlex.join([sys.executable, '-u', '-c', script])
        with session.shell('bash') as shell:
            with shell.enter(command, exit=chr(3)) as capture:
                self.assertIsNotNone(capture.expect('capture-ready', timeout=5))
            self.assertEqual(shell('printf alive', check=True).stdout, 'alive')

    def test_delayed_program_return_is_preserved_before_next_input(self):
        session = self.local()
        command = shlex.join([sys.executable, '-u', '-c',
                              "input('ready> '); import time; time.sleep(2)"])
        with session.shell('bash') as shell:
            with shell.enter(command, prompt='ready> ') as program:
                with self.assertRaises(TimeoutError):
                    program.input('quit', timeout=1)
                # The timeout must be the readiness wait, not a failed write.
                program.channel._raise_if_unusable()
                parent_prompt = program.channel.prompts[-2]
                deadline = time.monotonic() + 10
                while not any(parent_prompt in str(buffer) for buffer in
                              (program.channel._stdout, program.channel._stderr)):
                    self.assertLess(time.monotonic(), deadline,
                                    'fixture did not return to its parent shell')
                    time.sleep(.01)
                with patch.object(program.channel, 'send', wraps=program.channel.send) as send:
                    self.assertEqual(program.input('must-not-reach-shell'), 'exited')
                    send.assert_not_called()
            self.assertEqual(shell('printf parent-alive').stdout, 'parent-alive')

    def test_managed_continuous_output_explicit_stop(self):
        session = self.local()
        with session.start([sys.executable, '-u', '-c',
                            "import time; print('ready'); exec('while True: time.sleep(1)')"],
                           timeout=10, stop_timeout=1) as job:
            try:
                self.assertIn('ready', next(job.iter_stdout()))
            finally:
                result = job.stop()
            self.assertEqual(result.stop_reason, 'cancelled')
            self.assertEqual(result.termination_status, 'confirmed')
            self.assertIn('ready', result.stdout)
