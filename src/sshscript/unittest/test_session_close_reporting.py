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
