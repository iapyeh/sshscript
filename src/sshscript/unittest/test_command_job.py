"""Managed command contracts using processes and real Paramiko over socketpair."""
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

import paramiko
from session import Session, CommandTimeoutError
import sshscript
from commandjob import CommandJob


class Server(paramiko.ServerInterface):
    def __init__(self):
        self.processes = []
        self.workers = []
        self.release = threading.Event()

    def check_auth_none(self, username):
        return paramiko.AUTH_SUCCESSFUL

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED

    def check_channel_pty_request(self, *args):
        return True

    def check_channel_exec_request(self, channel, command):
        if command == b'exec stall-ack':
            self.release.wait(3)
            return False
        def execute():
            process = subprocess.Popen(command.decode(), shell=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                       start_new_session=True)
            self.processes.append(process)
            def pump(stream, send):
                try:
                    while data := os.read(stream.fileno(), 8192):
                        send(data)
                except (OSError, EOFError):
                    pass
            pumps = [threading.Thread(target=pump, args=(process.stdout, channel.sendall), daemon=True),
                     threading.Thread(target=pump, args=(process.stderr, channel.sendall_stderr), daemon=True)]
            for thread in pumps:
                thread.start()
            try:
                status = process.wait()
                for thread in pumps:
                    thread.join(1)
                if not channel.closed:
                    channel.send_exit_status(status)
                    channel.shutdown_write()
            except (OSError, EOFError):
                pass
            finally:
                channel.close()
                for stream in (process.stdout, process.stderr):
                    stream.close()
        thread = threading.Thread(target=execute, daemon=True)
        self.workers.append(thread)
        thread.start()
        return True


class CommandJobTests(unittest.TestCase):
    def local(self):
        session = Session()
        self.addCleanup(session.close)
        return session

    def remote(self):
        left, right = socket.socketpair()
        server_transport = paramiko.Transport(left)
        client_transport = paramiko.Transport(right)
        server_transport.add_server_key(paramiko.RSAKey.generate(1024))
        server = Server()
        server_transport.start_server(event=threading.Event(), server=server)
        client_transport.start_client(timeout=3)
        client_transport.auth_none('test')
        # Accept incoming channels so the server transport retains their lifetime.
        channels = []
        def accept():
            while server_transport.is_active():
                channel = server_transport.accept(0.1)
                if channel is not None:
                    channels.append(channel)
        acceptor = threading.Thread(target=accept, daemon=True)
        acceptor.start()
        client = paramiko.SSHClient()
        client._transport = client_transport
        session = self.local()
        session._client = client
        session.host = 'socketpair.test'
        def cleanup():
            server.release.set()
            client_transport.close()
            server_transport.close()
            for process in server.processes:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
            for worker in server.workers:
                worker.join(3)
            acceptor.join(1)
            left.close()
            right.close()
        self.addCleanup(cleanup)
        return session

    def command(self, source):
        return [sys.executable, '-u', '-c', source]

    def test_exports_and_success_on_both_backends(self):
        self.assertIs(sshscript.CommandTimeoutError, CommandTimeoutError)
        for session in (self.local(), self.remote()):
            with self.subTest(host=session.host):
                result = session(self.command('import sys; print("out"); print("err", file=sys.stderr)'), command_timeout=3)
                self.assertEqual((result.stdout, result.stderr, result.exitcode), ('out\n', 'err\n', 0))
                self.assertIs(result, session.last_result)
                self.assertEqual(session.stdout, 'out\n')
                self.assertEqual(result.stop_reason, 'completed')

    def test_continuous_output_does_not_reset_deadline(self):
        for session in (self.local(), self.remote()):
            with self.subTest(host=session.host):
                start = time.monotonic()
                with self.assertRaises(CommandTimeoutError) as caught:
                    session(self.command('import time\nwhile True:\n print("tick"); time.sleep(.01)'), command_timeout=.3, stop_timeout=.1)
                self.assertLess(time.monotonic() - start, 2)
                self.assertIn('tick', caught.exception.stdout)
                self.assertEqual(caught.exception.result.stop_reason, 'timeout')
                self.assertIsNone(session.last_result)
                self.assertEqual(caught.exception.termination_status, 'confirmed' if session.host is None else 'unknown')

    def test_silent_command_and_unconsumed_stdin_are_bounded(self):
        for session in (self.local(), self.remote()):
            start = time.monotonic()
            with self.assertRaises(CommandTimeoutError):
                session(self.command('import time; time.sleep(10)'), command_timeout=.15,
                        stop_timeout=.1, input=b'x' * 4_000_000)
            self.assertLess(time.monotonic() - start, 2)

    def test_signal_permission_error_requires_confirmed_child_exit(self):
        for status in (None, -signal.SIGINT):
            with self.subTest(status=status):
                job = object.__new__(CommandJob)
                job._process = Mock(pid=123, poll=Mock(return_value=status))
                job._channel = None
                job._signal_lock = threading.Lock()
                job._sent_local_signals = set()
                with patch('commandjob.os.killpg', side_effect=PermissionError):
                    if status is None:
                        with self.assertRaises(PermissionError):
                            job._signal()
                        self.assertEqual(job._sent_local_signals, set())
                    else:
                        job._signal()
                        self.assertEqual(job._sent_local_signals, {signal.SIGINT})

    def test_local_stop_allows_sigint_handler_to_flush(self):
        source = 'import signal,time,sys\ndef stop(*args):\n print("flushed"); sys.exit(0)\nsignal.signal(signal.SIGINT,stop)\nprint("ready")\nwhile True: time.sleep(.1)'
        with self.local().start(self.command(source), timeout=None, check=True) as job:
            self.assertIn('ready', next(job.iter_stdout()))
            result = job.stop()
            self.assertIn('flushed', result.stdout)
            self.assertEqual(result.stop_reason, 'cancelled')
            self.assertEqual(result.termination_status, 'confirmed')
            self.assertIs(job.stop(), result)
            self.assertIs(job.wait(), result)

    def test_stop_escalates_when_sigint_ignored(self):
        source = 'import signal,time\nsignal.signal(signal.SIGINT,signal.SIG_IGN)\nprint("ready")\nwhile True: time.sleep(.1)'
        with self.local().start(self.command(source), stop_timeout=.1) as job:
            next(job.iter_stdout())
            start = time.monotonic()
            result = job.stop()
            self.assertLess(time.monotonic() - start, 2)
            self.assertEqual(result.exitcode, -signal.SIGKILL)

    def test_remote_stop_unknown_keeps_transport_usable(self):
        session = self.remote()
        with session.start(self.command('import time; print("ready"); time.sleep(10)'), stop_timeout=.1) as job:
            next(job.iter_stdout())
            result = job.stop()
            self.assertEqual(result.termination_status, 'unknown')
            self.assertIsNone(result.exitcode)
        self.assertEqual(session(['printf', 'alive'], command_timeout=2).stdout, 'alive')

    def test_deadline_covers_exec_request_ack(self):
        start = time.monotonic()
        with self.assertRaises(CommandTimeoutError):
            self.remote()(['stall-ack'], command_timeout=.15, stop_timeout=.1)
        self.assertLess(time.monotonic() - start, 2)

    def test_deadline_runs_without_wait(self):
        job = self.local().start(self.command('import time; time.sleep(10)'), timeout=.1, stop_timeout=.1)
        self.assertTrue(job._done.wait(2))
        with self.assertRaises(CommandTimeoutError):
            job.wait()

    def test_capture_is_bounded_and_queue_overflow_visible(self):
        with self.local().start(self.command('import sys; sys.stdout.write("x"*2_000_000); sys.stderr.write("y"*2_000_000)'), capture_limit=100, timeout=3) as job:
            result = job.wait()
            self.assertEqual(result.stdout, 'x' * 100)
            self.assertEqual(result.stderr, 'y' * 100)
            self.assertTrue(result.stdout_truncated and result.stderr_truncated)
            with self.assertRaises(BufferError):
                list(job.iter_stdout())

    def test_large_stderr_drained_on_ssh(self):
        result = self.remote()(self.command('import sys; sys.stderr.write("y"*3_000_000); print("done")'), command_timeout=5, capture_limit=100)
        self.assertEqual(result.stdout, 'done\n')
        self.assertTrue(result.stderr_truncated)

    def test_local_input_env_and_utf8_stream(self):
        with self.local().start(self.command('import os,sys; print(os.environ["JOB_TEST"]); print(sys.stdin.read())'), input='中文', env={'JOB_TEST': 'yes'}) as job:
            self.assertEqual(''.join(job.iter_stdout()), 'yes\n中文\n')

    def test_context_and_session_close_stop_jobs(self):
        session = self.local()
        with session.start(self.command('import time; time.sleep(10)'), stop_timeout=.1) as job:
            pass
        self.assertTrue(job.done)
        job = session.start(self.command('import time; time.sleep(10)'), stop_timeout=.1)
        session.close(strict=True)
        self.assertTrue(job.done)

    def test_check_error_and_primary_exception_preserved(self):
        session = self.local()
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            session(self.command('import sys; sys.exit(7)'), command_timeout=2, check=True)
        self.assertIs(caught.exception.result, session.last_result)
        with self.assertRaisesRegex(ValueError, 'primary'):
            with session.start(self.command('import time; time.sleep(10)'), stop_timeout=.1):
                raise ValueError('primary')

    def test_invalid_options_never_launch(self):
        session = self.local()
        with patch('commandjob.subprocess.Popen') as popen:
            for value in (0, -1, float('nan'), float('inf')):
                with self.assertRaises(ValueError):
                    session.start(['true'], timeout=value)
            with self.assertRaises(TypeError):
                session.start(['true'], timeout=True)
            with self.assertRaises(ValueError):
                session(['true'], timeout=1, command_timeout=1)
            with self.assertRaises(ValueError):
                session.start(['true'], get_pty=True)
            popen.assert_not_called()

    def test_spy_managed_commands_and_start(self):
        namespace = sshscript.run_script(
            'result = $(["printf", "managed"], command_timeout=2)\n'
            'with $.start(["printf", "stream"], timeout=2) as job:\n'
            '    text = "".join(job.iter_stdout())\n'
            '    sibling = $(["printf", "same-session"], command_timeout=2)\n'
        )
        self.assertEqual(namespace['result'].stdout, 'managed')
        self.assertEqual(namespace['text'], 'stream')
        self.assertEqual(namespace['sibling'].stdout, 'same-session')

    def test_job_keeps_session_owner_alive(self):
        with Session().start(self.command('print("alive")'), timeout=2) as job:
            self.assertEqual(job.wait().stdout, 'alive\n')

    def test_remote_pty_sends_interrupt_and_retains_acknowledged_status(self):
        session = self.local()
        session.host = 'pty.test'
        session._client = Mock()
        channel = Mock()
        session._client.get_transport.return_value.open_session.return_value = channel
        interrupted = threading.Event()
        started = threading.Event()
        channel.closed = False
        channel.eof_received = False
        channel.recv_ready.return_value = False
        channel.recv_stderr_ready.return_value = False
        channel.exit_status_ready.side_effect = interrupted.is_set
        channel.exec_command.side_effect = lambda cmd: started.set()
        channel.send_ready.return_value = True
        def send(data):
            self.assertEqual(data, b'\x03')
            channel.eof_received = True
            interrupted.set()
            return 1
        channel.send.side_effect = send
        channel.recv_exit_status.return_value = 130
        with session.start(['tcpdump'], get_pty=True, check=True, stop_timeout=.2) as job:
            self.assertTrue(started.wait(1))
            result = job.stop()
            self.assertEqual(result.termination_status, 'confirmed')
            self.assertEqual(result.exitcode, 130)
            channel.shutdown_write.assert_not_called()

    def test_session_clear_preserves_managed_snapshot(self):
        session = self.local()
        result = session(['printf', 'saved'], command_timeout=2)
        session.clear()
        self.assertEqual(session.stdout, '')
        self.assertEqual(result.stdout, 'saved')
        self.assertIs(session.last_result, result)

    def test_legacy_timeout_unchanged(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.local()(self.command('import time; time.sleep(10)'), timeout=.05)


if __name__ == '__main__':
    unittest.main()
