"""Transfer contract tests using a local filesystem-backed SFTP double."""
import errno
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from session import Session
from errorutils import SSHScriptException


class LocalSFTP:
    def __init__(self, root):
        self.root = root
        self.before_open = lambda: None

    def path(self, path):
        return self.root / path.lstrip('/')

    def stat(self, path):
        return self.path(path).stat()

    def lstat(self, path):
        return self.path(path).lstat()

    def mkdir(self, path):
        self.path(path).mkdir()

    def put(self, src, dst):
        self.path(dst).write_bytes(Path(src).read_bytes())

    def get(self, src, dst):
        Path(dst).write_bytes(self.path(src).read_bytes())

    def open(self, path, mode):
        assert mode == 'wx', mode
        self.before_open()
        stream = self.path(path).open('xb')
        stream.set_pipelined = lambda enabled: None
        return stream


class ConnectionRequirementTests(unittest.TestCase):
    def test_unavailable_connections_rejected_before_file_access(self):
        from unittest.mock import Mock, PropertyMock
        clients = {
            'never connected': None,
            'inactive transport': Mock(get_transport=Mock(
                return_value=Mock(is_active=Mock(return_value=False)))),
            'no transport': Mock(get_transport=Mock(return_value=None)),
        }
        for state, client in clients.items():
            for method in ('upload', 'download'):
                with self.subTest(state=state, method=method):
                    session = Session()
                    session._client = client
                    try:
                        with patch('session.os.path.abspath') as abspath, \
                             patch('session.os.getcwd') as getcwd, \
                             patch.object(Session, 'sftp', new_callable=PropertyMock) as sftp:
                            args = (None, None) if method == 'upload' else (None,)
                            with self.assertRaisesRegex(
                                    SSHScriptException,
                                    method + r'\(\) requires an active SSH connection'):
                                getattr(session, method)(*args)
                            abspath.assert_not_called()
                            getcwd.assert_not_called()
                            sftp.assert_not_called()
                    finally:
                        session._client = None
                        session.close()


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.src = root / 'source.txt'
        self.src.write_bytes(b'new data' * 10000)
        remote = root / 'remote'
        remote.mkdir()
        self.sftp = LocalSFTP(remote)
        self.session = SimpleNamespace(connected=True, sftp=self.sftp,
                                       host='test', _lastDollar=SimpleNamespace(exitcode=7))

    def upload(self, dst, **kwargs):
        return Session.upload(self.session, self.src, dst, **kwargs)

    def test_destination_rules(self):
        self.sftp.path('/existing').mkdir()
        self.sftp.path('/source.txt').mkdir()
        cases = [('/existing', '/existing/source.txt'),
                 ('/source.txt', '/source.txt/source.txt'),
                 ('/new/', '/new/source.txt'),
                 ('/other/renamed.csv', '/other/renamed.csv'),
                 ('relative/noextension', 'relative/noextension')]
        for dst, resolved in cases:
            with self.subTest(dst=dst):
                result = self.upload(dst, makedirs=True)
                self.assertEqual(result, (str(self.src), resolved))
                self.assertEqual(self.sftp.path(resolved).read_bytes(), self.src.read_bytes())

    def test_existing_file_never_overwritten(self):
        for makedirs in (False, True):
            for dst in ('/source.txt', '/different.csv'):
                with self.subTest(makedirs=makedirs, dst=dst):
                    self.sftp.path(dst).write_bytes(b'original')
                    with self.assertRaises(FileExistsError):
                        self.upload(dst, makedirs=makedirs, overwrite=False)
                    self.assertEqual(self.sftp.path(dst).read_bytes(), b'original')

    def test_existing_directory_resolves_before_protection(self):
        self.sftp.path('/folder').mkdir()
        self.sftp.path('/folder/source.txt').write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            self.upload('/folder', overwrite=False)

    def test_creation_race_preserves_other_file(self):
        self.sftp.before_open = lambda: self.sftp.path('/race').write_bytes(b'other')
        with self.assertRaises(FileExistsError):
            self.upload('/race', overwrite=False)
        self.assertEqual(self.sftp.path('/race').read_bytes(), b'other')

    def test_exclusive_success_and_command_results(self):
        self.upload('/new/result', makedirs=True, overwrite=False)
        self.assertEqual(self.sftp.path('/new/result').read_bytes(), self.src.read_bytes())
        Session.download(self.session, '/new/result', str(self.src.parent / 'download'))
        self.assertEqual(Session.exitcode.fget(self.session), 7)

    def test_overwrite_true(self):
        self.sftp.path('/source.txt').write_bytes(b'old')
        self.upload('/source.txt')
        self.assertEqual(self.sftp.path('/source.txt').read_bytes(), self.src.read_bytes())

    def test_missing_parent_and_file_with_trailing_slash(self):
        with self.assertRaises(FileNotFoundError):
            self.upload('/missing/file')
        self.sftp.path('/file').touch()
        with self.assertRaises(NotADirectoryError):
            self.upload('/file/', makedirs=True)

    def test_dangling_symlink_is_protected(self):
        self.sftp.path('/link').symlink_to(self.sftp.path('/absent'))
        with self.assertRaises(FileExistsError):
            self.upload('/link', overwrite=False)
        self.assertFalse(self.sftp.path('/absent').exists())

    def test_open_errors_propagate_without_fallback(self):
        for error in (PermissionError(errno.EACCES, 'denied'), OSError('SFTP failure')):
            with self.subTest(error=error):
                with patch.object(self.sftp, 'open', side_effect=error), patch.object(self.sftp, 'put') as put:
                    with self.assertRaises(type(error)) as caught:
                        self.upload('/new', overwrite=False)
                    self.assertIs(caught.exception, error)
                    put.assert_not_called()

    def test_write_failure_propagates_and_keeps_command_result(self):
        from unittest.mock import MagicMock
        destination = MagicMock()
        error = OSError('connection lost during write')
        destination.__enter__.return_value.write.side_effect = error
        with patch.object(self.sftp, 'open', return_value=destination):
            with self.assertRaises(OSError) as caught:
                self.upload('/new', overwrite=False)
            self.assertIs(caught.exception, error)
        self.assertEqual(Session.exitcode.fget(self.session), 7)

    def test_paramiko_exclusive_open_includes_write_flag(self):
        import paramiko
        from paramiko.sftp import CMD_HANDLE, SFTP_FLAG_WRITE, SFTP_FLAG_CREATE, SFTP_FLAG_EXCL
        from unittest.mock import MagicMock
        client = MagicMock()
        client._adjust_cwd.return_value = b'/target'
        message = MagicMock()
        message.get_binary.return_value = b'handle'
        client._request.return_value = (CMD_HANDLE, message)
        with patch('paramiko.sftp_client.SFTPFile'):
            paramiko.SFTPClient.open(client, '/target', 'wx')
        flags = client._request.call_args.args[2]
        for flag in (SFTP_FLAG_WRITE, SFTP_FLAG_CREATE, SFTP_FLAG_EXCL):
            self.assertTrue(flags & flag)

    def test_size_mismatch_raises(self):
        original = self.sftp.stat
        def wrong_size(path):
            result = original(path)
            return SimpleNamespace(st_mode=result.st_mode, st_size=result.st_size + 1)
        with patch.object(self.sftp, 'stat', side_effect=wrong_size):
            with self.assertRaisesRegex(OSError, 'size mismatch'):
                self.upload('/new', overwrite=False)


if __name__ == '__main__':
    unittest.main()
