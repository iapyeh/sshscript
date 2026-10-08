"""Tests that session cleanup failures cannot masquerade as success."""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import sshscript
from session import Session


class FailingSocket:
    def close(self):
        raise OSError('simulated socket close failure')


class NoOpClient:
    def get_transport(self):
        return None

    def close(self):
        pass


class SessionCloseReportingTests(unittest.TestCase):
    def make_failing_session(self, remote=False):
        session = Session()
        session._sock = FailingSocket()
        if remote:
            session._client = NoOpClient()
        return session

    def test_close_inside_shell_is_rejected_without_partial_cleanup(self):
        session = Session()
        self.addCleanup(session.close)
        with session.shell('bash', get_pty=False) as shell:
            process = shell.channel.cp
            with session.start(['sleep', '30'], stop_timeout=.1) as job:
                for strict in (False, True):
                    with self.assertRaisesRegex(RuntimeError, 'console context is active'):
                        session.close(strict=strict)
                    self.assertFalse(session.closed)
                    self.assertFalse(job.done)
                    self.assertFalse(shell.closed)
                    self.assertIsNone(process.poll())
                    self.assertEqual(session.close_errors, ())
                # Replacing _lastDollar must not bypass the active-console guard.
                session.exec_command(['printf', 'one-shot'], check=True)
                with self.assertRaises(RuntimeError):
                    session.disconnect()
                shell('printf alive', check=True)
                self.assertIn('alive', str(shell.stdout))
        self.assertIsNotNone(process.poll())
        self.assertTrue(session.close(strict=True))
        self.assertTrue(session.close(strict=True))

    def test_parent_close_preflights_all_children_before_cleanup(self):
        parent = Session()
        child = Session(parent)
        sibling = Session(parent)
        parent.subsessions.extend((child, sibling))
        self.addCleanup(parent.close)
        with child.shell('bash', get_pty=False) as shell:
            with self.assertRaisesRegex(RuntimeError, 'console context is active'):
                parent.close(strict=True)
            self.assertFalse(parent.closed)
            self.assertFalse(child.closed)
            self.assertFalse(sibling.closed)
            self.assertEqual(parent.subsessions, [child, sibling])
            shell('printf child-alive')
            self.assertIn('child-alive', str(shell.stdout))
        child.close(strict=True)
        self.assertFalse(parent.closed)
        self.assertEqual(parent.exec_command(['printf', 'parent-alive']).stdout, 'parent-alive')
        parent.close(strict=True)
        self.assertTrue(sibling.closed)

    def test_nested_console_return_and_exception_release_guard(self):
        session = Session()
        self.addCleanup(session.close)
        def work():
            with session.shell('bash', get_pty=False) as shell:
                with shell.shell('bash'):
                    with self.assertRaises(RuntimeError):
                        session.close()
                    return
        work()
        self.assertFalse(session._active_consoles)
        with self.assertRaisesRegex(ValueError, 'body failed'):
            with session.shell('bash', get_pty=False):
                raise ValueError('body failed')
        self.assertFalse(session._active_consoles)
        session.close(strict=True)

    def test_console_entry_and_exit_failures_release_tracking(self):
        from channelutils import ShellConsole
        session = Session()
        self.addCleanup(session.close)
        context = session.shell('bash', get_pty=False)
        with mock.patch.object(ShellConsole, '__enter__', side_effect=ValueError('entry failed')):
            with self.assertRaisesRegex(ValueError, 'entry failed'):
                with context:
                    self.fail('entry failure must not execute the body')
        self.assertFalse(session._active_consoles)
        self.assertTrue(context.channel.closed)
        context = session.shell('bash', get_pty=False)
        context.__enter__()
        with mock.patch.object(context.innerConsole, '__exit__', side_effect=ValueError('exit failed')):
            with self.assertRaisesRegex(ValueError, 'exit failed'):
                context.__exit__(None, None, None)
        self.assertFalse(session._active_consoles)
        session.close(strict=True)

    def test_unentered_console_is_closed_and_cannot_be_entered_later(self):
        session = Session()
        context = session.shell('bash', get_pty=False)
        process = context.channel.cp
        session.close(strict=True)
        self.assertTrue(context.channel.closed)
        self.assertIsNotNone(process.poll())
        with self.assertRaisesRegex(RuntimeError, 'closed session'):
            context.__enter__()

    def test_closed_session_rejects_new_work_even_after_cleanup_failure(self):
        for session in (Session(), self.make_failing_session()):
            session.close()
            operations = (
                lambda: session.exec_command(['true']),
                lambda: session.start(['true']),
                lambda: session.connect('example.invalid'),
                lambda: session.shell(),
                lambda: session.su('root'),
                lambda: session.sudo(),
                lambda: session.enter('bash'),
                lambda: session.pkey('/unused-key'),
                lambda: session.run('raise AssertionError("executed")'),
                session.__enter__,
                lambda: session.console_info,
                lambda: session.sftp,
                lambda: session.upload('/unused', '/unused'),
                lambda: session.download('/unused'),
            )
            for operation in operations:
                with self.subTest(operation=operation):
                    with self.assertRaises((RuntimeError, sshscript.SSHScriptException)):
                        operation()

    def test_best_effort_close_reports_and_retains_failures(self):
        session = self.make_failing_session()

        result = session.close()

        self.assertFalse(result)
        self.assertTrue(session.closed)
        self.assertEqual(len(session.close_errors), 1)
        self.assertEqual(session.close_errors[0][0], 'close SSH socket')
        self.assertIsInstance(session.close_errors[0][1], OSError)
        self.assertFalse(session.close())

    def test_strict_close_raises_after_finishing_cleanup(self):
        session = self.make_failing_session()

        with self.assertRaisesRegex(
            RuntimeError,
            'session cleanup failed.*close SSH socket',
        ):
            session.close(strict=True)

        self.assertTrue(session.closed)
        self.assertIsNone(session._sock)
        with self.assertRaises(RuntimeError):
            session.close(strict=True)

    def test_context_exit_reports_cleanup_failure_after_success(self):
        session = self.make_failing_session(remote=True)

        with self.assertRaisesRegex(
            RuntimeError,
            'session cleanup failed.*close SSH socket',
        ):
            with session:
                pass

        self.assertTrue(session.closed)
        self.assertEqual(session.close_errors[0][0], 'close SSH socket')

    def test_context_exit_preserves_primary_exception(self):
        session = self.make_failing_session(remote=True)

        with self.assertRaisesRegex(ValueError, 'primary failure') as caught:
            with session:
                raise ValueError('primary failure')

        self.assertTrue(session.closed)
        self.assertIn(
            'session cleanup also failed',
            ' '.join(caught.exception.__notes__),
        )

    def test_run_script_reports_cleanup_failure_after_success(self):
        session = self.make_failing_session()

        with mock.patch.object(sshscript, 'Session', return_value=session):
            with self.assertRaisesRegex(
                RuntimeError,
                'session cleanup failed.*close SSH socket',
            ):
                sshscript.run_script('answer = 42')

        self.assertTrue(session.closed)

    def test_run_script_preserves_primary_exception(self):
        session = self.make_failing_session()

        with mock.patch.object(sshscript, 'Session', return_value=session):
            with self.assertRaisesRegex(ValueError, 'primary failure') as caught:
                sshscript.run_script("raise ValueError('primary failure')")

        self.assertIn(
            'session cleanup also failed',
            ' '.join(caught.exception.__notes__),
        )

    def test_run_script_cleanup_failure_overrides_exit_signal(self):
        session = self.make_failing_session()
        with mock.patch.object(
            session,
            'run',
            side_effect=sshscript.SSHScriptExit('requested exit', 0),
        ), mock.patch.object(sshscript, 'Session', return_value=session):
            with self.assertRaisesRegex(
                RuntimeError,
                'session cleanup failed.*close SSH socket',
            ):
                sshscript.run_script('ignored source')

    def test_run_file_reports_cleanup_failure_after_success(self):
        session = self.make_failing_session()
        with tempfile.TemporaryDirectory(
            prefix='sshscript-cleanup-success-'
        ) as folder:
            script = Path(folder) / 'success.spy'
            script.write_text('answer = 42\n', encoding='utf-8')

            with mock.patch.object(sshscript, 'Session', return_value=session):
                with self.assertRaisesRegex(
                    RuntimeError,
                    'session cleanup failed.*close SSH socket',
                ):
                    sshscript.run_file(script)

        self.assertTrue(session.closed)

    def test_run_file_preserves_primary_exception(self):
        session = self.make_failing_session()
        with tempfile.TemporaryDirectory(
            prefix='sshscript-cleanup-failure-'
        ) as folder:
            script = Path(folder) / 'failure.spy'
            script.write_text(
                "raise ValueError('primary failure')\n",
                encoding='utf-8',
            )

            with mock.patch.object(sshscript, 'Session', return_value=session):
                with self.assertRaisesRegex(
                    ValueError,
                    'primary failure',
                ) as caught:
                    sshscript.run_file(script)

        self.assertIn(
            'session cleanup also failed',
            ' '.join(caught.exception.__notes__),
        )

    def test_run_file_cleanup_failure_overrides_break_status(self):
        session = self.make_failing_session()
        with tempfile.TemporaryDirectory(
            prefix='sshscript-cleanup-break-'
        ) as folder:
            script = Path(folder) / 'break.spy'
            script.write_text('ignored source\n', encoding='utf-8')

            with mock.patch.object(
                session,
                'run',
                side_effect=sshscript.SSHScriptBreak('requested break', 37),
            ), mock.patch.object(sshscript, 'Session', return_value=session):
                with self.assertRaisesRegex(
                    RuntimeError,
                    'session cleanup failed.*close SSH socket',
                ):
                    sshscript.run_file(script)


if __name__ == '__main__':
    unittest.main(verbosity=2)
