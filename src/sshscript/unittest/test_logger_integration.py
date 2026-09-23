"""Credential-free integration tests for SSHScript logging behavior."""

from io import StringIO
import logging
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import errorutils
import session as session_module
from session import Session


class LoggerIntegrationTests(unittest.TestCase):
    def capture_sshscript_logs(self):
        wrapped = errorutils.get_logger()
        original_logger = wrapped._logger
        capture = StringIO()
        test_logger = logging.getLogger('sshscript.integration')
        test_logger.handlers.clear()
        test_logger.propagate = False
        test_logger.setLevel(logging.DEBUG)
        test_logger.addHandler(logging.StreamHandler(capture))
        errorutils.set_logger(test_logger)

        def restore():
            wrapped.set_logger(original_logger, keep_level=False)
            test_logger.handlers.clear()

        self.addCleanup(restore)
        return capture

    def test_local_command_logs_metadata_without_command_secret(self):
        capture = self.capture_sshscript_logs()
        secret = 'SSHSCRIPT_SECRET_DO_NOT_LOG_9274'
        command = shlex.join(
            [
                sys.executable,
                '-c',
                "print('logger-integration-ok')",
                '--password',
                secret,
            ]
        )
        session = Session()
        self.addCleanup(session.close)

        stdout, stderr = session.exec_command(command, shell=False, timeout=10)

        self.assertEqual(str(stdout), 'logger-integration-ok\n')
        self.assertEqual(str(stderr), '')
        self.assertEqual(session.exitcode, 0)
        self.assertIn('Executing subprocess', capture.getvalue())
        self.assertNotIn(secret, capture.getvalue())

    def test_connection_timeout_is_not_swallowed(self):
        class FailingSSHClient:
            def load_system_host_keys(self):
                pass

            def set_missing_host_key_policy(self, policy):
                pass

            def connect(self, *args, **kwargs):
                raise TimeoutError('simulated timeout')

        session = Session()
        self.addCleanup(session.close)
        with patch.object(
            session_module.paramiko,
            'SSHClient',
            return_value=FailingSSHClient(),
        ):
            with self.assertRaisesRegex(TimeoutError, 'simulated timeout'):
                session.connect(
                    'example.invalid',
                    username='test-user',
                    password='test-password',
                )

    def test_cli_error_log_does_not_include_exception_secret(self):
        secret = 'SSHSCRIPT_EXCEPTION_SECRET_DO_NOT_LOG_1742'
        source_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory(
            prefix='sshscript-logger-cli-'
        ) as folder:
            script = Path(folder) / 'raise-secret.spy'
            script.write_text(
                f"raise RuntimeError({secret!r})\n",
                encoding='utf-8',
            )
            completed = subprocess.run(
                [sys.executable, str(source_root / 'sshscript.py'), str(script)],
                cwd=source_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn('SSHScript CLI failed', completed.stderr)
        self.assertIn('exception_type=RuntimeError', completed.stderr)
        self.assertNotIn(secret, completed.stderr)
        self.assertNotIn(' INFO sshscript ', completed.stdout)

    def test_local_command_timeout_is_propagated_from_worker(self):
        command = shlex.join(
            [
                sys.executable,
                '-c',
                'import time; time.sleep(1)',
            ]
        )
        session = Session()
        self.addCleanup(session.close)

        with self.assertRaises(subprocess.TimeoutExpired):
            session.exec_command(command, shell=False, timeout=0.01)

    def test_unexpected_upload_directory_error_is_not_swallowed(self):
        class FailingSFTP:
            def getcwd(self):
                return '/remote'

            def stat(self, path):
                raise PermissionError(f'cannot inspect {path}')

            def close(self):
                pass

        class FakeSSHClient:
            class Transport:
                def is_active(self):
                    return True

            def get_transport(self):
                return self.Transport()

            def close(self):
                pass

        session = Session()
        session._host = 'example.invalid'
        session._port = 22
        session._username = 'test-user'
        session._client = FakeSSHClient()
        session._sftp = FailingSFTP()
        self.addCleanup(session.close)

        with tempfile.TemporaryDirectory(
            prefix='sshscript-logger-upload-'
        ) as folder:
            source = Path(folder) / 'source.txt'
            source.write_text('content', encoding='utf-8')

            with self.assertRaisesRegex(PermissionError, 'cannot inspect'):
                session.upload(
                    str(source),
                    'missing/destination.txt',
                    makedirs=True,
                )

    def test_transfer_info_logs_do_not_disclose_host_or_paths(self):
        class SFTP:
            def stat(self, path):
                raise FileNotFoundError(path)

            def put(self, source, destination):
                self.uploaded = Path(source).read_bytes()

            def get(self, source, destination):
                Path(destination).write_bytes(b'downloaded')

            def close(self):
                pass

        class SSHClient:
            class Transport:
                def is_active(self):
                    return True

            def get_transport(self):
                return self.Transport()

            def close(self):
                pass

        capture = self.capture_sshscript_logs()
        session = Session()
        session._host = 'private-host.example.invalid'
        session._port = 22
        session._username = 'private-user'
        session._client = SSHClient()
        session._sftp = SFTP()
        self.addCleanup(session.close)

        with tempfile.TemporaryDirectory(
            prefix='sshscript-private-transfer-'
        ) as folder:
            source = Path(folder) / 'private-source-name.txt'
            destination = Path(folder) / 'private-download-name.txt'
            source.write_text('content', encoding='utf-8')
            remote_upload = '/private/remote/upload-name.txt'
            remote_download = '/private/remote/download-name.txt'

            session.upload(str(source), remote_upload)
            session.download(remote_download, str(destination))
            logs = capture.getvalue()

        self.assertIn('Starting upload', logs)
        self.assertIn('Upload completed', logs)
        self.assertIn('Starting download', logs)
        self.assertIn('Download completed', logs)
        for private_value in (
            session.host,
            str(source),
            str(destination),
            remote_upload,
            remote_download,
        ):
            self.assertNotIn(private_value, logs)


if __name__ == '__main__':
    unittest.main(verbosity=2)
