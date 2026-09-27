"""Command boundaries and immutable results on local and fake SSH backends."""
from dataclasses import FrozenInstanceError
import json
import shlex
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from session import Session
import sshscript


class CommandAPITests(unittest.TestCase):
    def local(self):
        session = Session()
        self.addCleanup(session.close)
        return session

    def remote(self, stdout=b'out', stderr=b'err', status=7):
        session = self.local()
        session.host = 'example.test'
        client = Mock()
        client.get_transport.return_value.is_active.return_value = True
        channel = Mock()
        channel.recv_exit_status.return_value = status
        output, error, stdin = Mock(), Mock(), Mock()
        output.read.return_value, error.read.return_value = stdout, stderr
        output.channel = error.channel = stdin.channel = channel
        client.exec_command.return_value = stdin, output, error
        session._client = client
        return session, client

    def test_argv_preserves_empty_spaces_quotes_newlines_and_metacharacters(self):
        args = ['', 'a b', "a'b", 'x; echo injected', '$HOME', '|', 'a\nb', '*.py']
        session = self.local()
        result = session([sys.executable, '-c', 'import sys,json; print(json.dumps(sys.argv[1:]))', *args])
        self.assertEqual(json.loads(result.stdout), args)
        self.assertEqual(result.exitcode, 0)
        self.assertFalse(session.dollar.use_shell)

    def test_result_is_snapshot_and_supports_three_value_unpacking(self):
        session = self.local()
        args = ['printf', 'first']
        first = session(args)
        args[1] = 'mutated'
        session(['printf', 'second'])
        session.close()
        self.assertEqual(first.command, ('printf', 'first'))
        self.assertEqual(tuple(first), ('first', '', 0))
        stdout, stderr, exitcode = first
        self.assertEqual((stdout, stderr, exitcode), ('first', '', 0))
        self.assertEqual(first[-1], 0)
        self.assertEqual(first[:], ('first', '', 0))
        with self.assertRaises(ValueError):
            stdout, stderr = first
        self.assertEqual(first[0], 'first')
        self.assertEqual(len(first), 3)
        self.assertIsNone(first.host)
        self.assertGreaterEqual(first.duration, 0)
        with self.assertRaises(FrozenInstanceError):
            first.exitcode = 9

    def test_check_preserves_failure_result_on_both_backends(self):
        remote, client = self.remote()
        for session in (self.local(), remote):
            with self.subTest(host=session.host):
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    session([sys.executable, '-c', 'import sys; print("out",end=""); print("err",end="",file=sys.stderr); sys.exit(7)'], check=True)
                error = caught.exception
                self.assertEqual((error.returncode, error.stdout, error.stderr), (7, 'out', 'err'))
                self.assertIs(error.result, session.last_result)
                self.assertEqual(session.exitcode, 7)
                self.assertEqual(str(session.stdout), 'out')
                self.assertEqual(error.result.host, session.host)
        self.assertNotIn('check', client.exec_command.call_args.kwargs)

    def test_check_false_returns_nonzero_and_remote_quotes_argv(self):
        remote, client = self.remote()
        args = ['printf', '%s', 'a; b', '', '$HOME', "a'b"]
        result = remote(args, check=False)
        self.assertEqual(result.exitcode, 7)
        self.assertEqual(shlex.split(client.exec_command.call_args.args[0]), ['exec', *args])
        self.assertNotIn('check', client.exec_command.call_args.kwargs)

    def test_success_with_check_and_remote_host_snapshot(self):
        remote, _ = self.remote(status=0)
        result = remote('true', check=True)
        remote.host = 'other.test'
        self.assertEqual(result.host, 'example.test')
        self.assertEqual(result.exitcode, 0)

    def test_transport_errors_propagate_and_disconnected_remote_never_runs_locally(self):
        remote, client = self.remote()
        client.exec_command.side_effect = TimeoutError('transport timeout')
        with self.assertRaises(TimeoutError):
            remote('true', check=True)
        self.assertIsNone(remote.last_result)
        client.get_transport.return_value.is_active.return_value = False
        with patch('dollar.subprocess.run') as run:
            with self.assertRaises(BrokenPipeError):
                remote('true')
        run.assert_not_called()

    def test_invalid_arguments_never_execute(self):
        session = self.local()
        for args, kwargs, error in [
            ([], {}, ValueError), ([''], {}, ValueError),
            (['printf', 3], {}, TypeError), (['printf', '\x00'], {}, ValueError),
            (['true'], {'shell': True}, ValueError),
            (['true'], {'shell': 'bash'}, ValueError),
            (['true'], {'shell_executable': '/bin/sh'}, ValueError),
            ('true', {'check': 'yes'}, TypeError),
        ]:
            with self.subTest(args=args, kwargs=kwargs), patch('dollar.subprocess.run') as run:
                with self.assertRaises(error):
                    session(args, **kwargs)
                run.assert_not_called()

    def test_spy_check_maps_exception_to_original_command(self):
        source = 'result = $(["sh", "-c", "exit 7"], check=True)\n'
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            sshscript.run_script(source)
        self.assertEqual(caught.exception.result.exitcode, 7)


if __name__ == '__main__':
    unittest.main()
