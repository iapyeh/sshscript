"""Managed command contracts using processes and real Paramiko over socketpair."""
import os
import io
import hashlib
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

import paramiko
from session import Session, CommandTimeoutError
import sshscript
from commandjob import CommandJob


class Server(paramiko.ServerInterface):
    def __init__(self):
        self.processes = []
        self.workers = []
        self.release = threading.Event()
        self.errors = []

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
        if command == b'exec drop-status':
            def drop_status():
                # EOF is sent only after the exec request was acknowledged.
                while channel.recv(8192):
                    pass
                channel.sendall(b'observed-before-close')
                channel.shutdown_write()
                channel.close()
            worker = threading.Thread(target=drop_status, daemon=True)
            self.workers.append(worker)
            worker.start()
            return True
        def execute():
            process = subprocess.Popen(command.decode(), shell=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, stdin=subprocess.PIPE,
                                       start_new_session=True)
            self.processes.append(process)
            def pump(stream, send):
                try:
                    while data := os.read(stream.fileno(), 8192):
                        send(data)
                except (OSError, EOFError) as exc:
                    if not channel.closed:
                        self.errors.append(exc)
                finally:
                    stream.close()
            def feed_input():
                try:
                    while data := channel.recv(8192):
                        process.stdin.write(data)
                        process.stdin.flush()
                except (BrokenPipeError, EOFError, OSError):
                    # Early process exit / channel cancellation closes stdin.
                    pass
                finally:
                    try:
                        process.stdin.close()
                    except BrokenPipeError:
                        pass
            pumps = [threading.Thread(target=pump, args=(process.stdout, channel.sendall), daemon=True),
                     threading.Thread(target=pump, args=(process.stderr, channel.sendall_stderr), daemon=True),
                     threading.Thread(target=feed_input, daemon=True)]
            self.workers.extend(pumps)
            for thread in pumps:
                thread.start()
            try:
                status = process.wait()
                for thread in pumps[:2]:
                    thread.join(3)
                    if thread.is_alive():
                        raise RuntimeError('fixture output pump did not finish')
                if not channel.closed:
                    channel.send_exit_status(status)
                    channel.shutdown_write()
            except (OSError, EOFError) as exc:
                if not channel.closed:
                    self.errors.append(exc)
            except Exception as exc:
                self.errors.append(exc)
            finally:
                channel.close()
                pumps[2].join(3)
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
        # Force flow control well before the bulk test payload is exhausted.
        server_transport = paramiko.Transport(left, default_window_size=32768)
        client_transport = paramiko.Transport(right, default_window_size=32768)
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
        session._test_server = server
        session._test_server_transport = server_transport
        session._test_client_transport = client_transport
        session._test_channels = channels
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
            self.assertFalse(acceptor.is_alive(), 'fixture acceptor leaked')
            self.assertFalse(any(worker.is_alive() for worker in server.workers),
                             'fixture process I/O worker leaked')
            self.assertEqual(server.errors, [], 'fixture failed to deliver output')
        self.addCleanup(cleanup)
        return session

    def command(self, source):
        return [sys.executable, '-u', '-c', source]

    def assert_job_released(self, job):
        for thread in (job._worker, job._monitor):
            thread.join(2)
            self.assertFalse(thread.is_alive(), 'owned job thread leaked')
        if job._process is not None:
            self.assertIsNotNone(job._process.poll())
            for stream in (job._process.stdin, job._process.stdout, job._process.stderr):
                self.assertTrue(stream.closed, 'owned subprocess pipe leaked')
        if job._channel is not None:
            self.assertTrue(job._channel.closed, 'owned SSH channel leaked')

    def test_full_duplex_bulk_transfer_and_eof(self):
        # Write more than the SSH/pipe window BEFORE reading input. Sequential
        # write-all-stdin then read-output implementations deadlock here.
        payload = bytes(range(256)) * 2048 + '中文\r\n'.encode()
        source = (
            'import sys,hashlib; '
            'sys.stdout.buffer.write(b"O"*262144); sys.stdout.flush(); '
            'sys.stderr.buffer.write(b"E"*262144); sys.stderr.flush(); '
            'data=sys.stdin.buffer.read(); '
            'print("\\nINPUT:"+hashlib.sha256(data).hexdigest()); '
            'sys.stderr.write("\\nEOF:"+str(len(data))+"\\n")'
        )
        for session in (self.local(), self.remote()):
            for mode in ('legacy', 'managed', 'start'):
                with self.subTest(host=session.host, mode=mode):
                    if mode == 'start':
                        with session.start(self.command(source), input=payload,
                                           timeout=10, capture_limit=1048576, check=True) as job:
                            result = job.wait()
                        self.assert_job_released(job)
                    else:
                        timing = {'timeout': 10} if mode == 'legacy' else {'command_timeout': 10}
                        result = session(self.command(source), input=payload, check=True, **timing)
                    self.assertEqual(result.stdout, 'O'*262144 + '\nINPUT:' + hashlib.sha256(payload).hexdigest() + '\n')
                    self.assertEqual(result.stderr, 'E'*262144 + '\nEOF:' + str(len(payload)) + '\n')
                    self.assertEqual(result.exitcode, 0)

    def test_empty_stdin_delivers_eof_on_both_backends(self):
        for session in (self.local(), self.remote()):
            for payload in ('', b''):
                with self.subTest(host=session.host, payload=payload):
                    with session.start(self.command('import sys; print(len(sys.stdin.buffer.read()))'),
                                       input=payload, timeout=3, check=True) as job:
                        self.assertEqual(job.wait().stdout, '0\n')
                    self.assert_job_released(job)

    def test_missing_ssh_exit_status_is_failure_not_a_completed_result(self):
        session = self.remote()
        for mode in ('legacy', 'managed'):
            with self.subTest(mode=mode):
                timing = {'timeout': 3} if mode == 'legacy' else {'command_timeout': 3}
                with self.assertRaises(EOFError):
                    session(['drop-status'], check=True, **timing)
                self.assertIsNone(session.last_result)
                self.assertIn('observed-before-close', str(session.stdout))
                # Losing one channel's exit status must not close the transport.
                self.assertEqual(session(['printf', 'alive'], command_timeout=3).stdout, 'alive')

    def test_legacy_blocked_stdin_timeout_releases_io_workers_and_channel(self):
        session = self.remote()
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            session(self.command('import time; print("ready"); time.sleep(30)'),
                    input=b'x'*1048576, timeout=.2)
        self.assertLess(time.monotonic() - started, 3)
        self.assertFalse(session.dollar.call_thread.is_alive())
        self.assertIsNone(session.last_result)
        self.assertEqual(session(['printf', 'alive'], command_timeout=3).stdout, 'alive')

    def test_disconnect_preserves_observed_output_and_never_falls_back_locally(self):
        session = self.remote()
        retained = session(['printf', 'previous'], command_timeout=3)
        job = session.start(self.command('import time; print("ready"); time.sleep(30)'),
                            timeout=5, stop_timeout=.2)
        self.addCleanup(lambda: job.stop() if not job.done else None)
        observed = ''
        for chunk in job.iter_stdout():
            observed += chunk
            if 'ready' in observed:
                break
        session._test_server_transport.close()
        with self.assertRaises((EOFError, OSError, paramiko.SSHException)) as caught:
            job.wait()
        self.assertNotIsInstance(caught.exception, CommandTimeoutError)
        self.assertIn('ready', job.stdout)
        self.assert_job_released(job)
        self.assertIs(session.last_result, retained)
        self.assertEqual(retained.stdout, 'previous')
        with patch('commandjob.subprocess.Popen') as managed, patch('dollar.subprocess.run') as legacy:
            for operation in (lambda: session(['printf', 'wrong-host']),
                              lambda: session.start(['printf', 'wrong-host'])):
                with self.assertRaises(BrokenPipeError):
                    operation()
            managed.assert_not_called()
            legacy.assert_not_called()

    def test_repeated_completion_timeout_and_stop_release_owned_resources(self):
        fd_dir = '/proc/self/fd' if os.path.isdir('/proc/self/fd') else '/dev/fd'
        baseline = len(os.listdir(fd_dir)) if os.path.isdir(fd_dir) else None
        for backend in ('local', 'ssh'):
            for cycle in range(3):
                with self.subTest(backend=backend, cycle=cycle):
                    session = self.local() if backend == 'local' else self.remote()
                    with session.start(self.command('print("complete")'), timeout=3) as job:
                        self.assertEqual(job.wait().stdout, 'complete\n')
                    self.assert_job_released(job)
                    with session.start(self.command('import time; print("ready"); time.sleep(30)'),
                                       timeout=3, stop_timeout=.1) as job:
                        for chunk in job.iter_stdout():
                            if 'ready' in chunk:
                                break
                        stopped = job.stop()
                        self.assertEqual(stopped.stop_reason, 'cancelled')
                        self.assertEqual(stopped.termination_status,
                                         'confirmed' if backend == 'local' else 'unknown')
                    self.assert_job_released(job)
                    job = session.start(self.command('import time; time.sleep(30)'),
                                        timeout=.1, stop_timeout=.1)
                    with self.assertRaises(CommandTimeoutError):
                        job.wait()
                    self.assert_job_released(job)
                    session.close(strict=True)
                    if backend == 'ssh':
                        for transport in (session._test_client_transport, session._test_server_transport):
                            transport.join(2)
                            self.assertFalse(transport.is_alive(), 'SSH transport thread leaked')
        # Dispose the fixture's server-side processes; channel closure alone
        # intentionally does not promise their termination.
        self.doCleanups()
        if baseline is not None:
            self.assertLessEqual(len(os.listdir(fd_dir)), baseline, 'file descriptors accumulated')

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
                job._process = Mock(pid=123, poll=Mock(return_value=status),
                                    wait=Mock(side_effect=subprocess.TimeoutExpired('sleep', 1)))
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

    def test_signal_permission_error_waits_for_delayed_child_exit(self):
        job = object.__new__(CommandJob)
        job._process = Mock(pid=123, poll=Mock(return_value=None),
                            wait=Mock(return_value=-signal.SIGINT))
        job._channel = None
        job._signal_lock = threading.Lock()
        job._sent_local_signals = set()
        job._status = None
        with patch('commandjob.os.killpg', side_effect=PermissionError):
            job._signal(force=True)
            job._signal()
            job._signal(force=True)
        job._process.wait.assert_called_once_with(timeout=1)
        self.assertEqual(job._status, -signal.SIGINT)
        self.assertEqual(job._sent_local_signals, {signal.SIGKILL})

    def test_local_signal_failure_still_closes_all_streams(self):
        job = object.__new__(CommandJob)
        job._argv = ['sleep', '30']
        job._env = None
        job._reason = 'cancelled'
        failure = PermissionError('signal denied')
        job._signal = Mock(side_effect=failure)
        streams = [io.BytesIO() for _ in range(3)]
        process = Mock(poll=Mock(return_value=None),
                       stdin=streams[0], stdout=streams[1], stderr=streams[2])
        with patch('commandjob.subprocess.Popen', return_value=process):
            with self.assertRaises(PermissionError) as caught:
                job._run_local()
        self.assertIs(caught.exception, failure)
        self.assertTrue(all(stream.closed for stream in streams))

    def test_stream_close_failures_do_not_replace_command_failure(self):
        for failed_index in range(3):
            with self.subTest(stream=failed_index):
                job = object.__new__(CommandJob)
                job._argv, job._env, job._reason = ['sleep', '30'], None, 'cancelled'
                primary = PermissionError('signal denied')
                job._signal = Mock(side_effect=primary)
                streams = [Mock() for _ in range(3)]
                streams[failed_index].close.side_effect = OSError('close denied')
                process = Mock(poll=Mock(return_value=None),
                               stdin=streams[0], stdout=streams[1], stderr=streams[2])
                with patch('commandjob.subprocess.Popen', return_value=process):
                    with self.assertRaises(PermissionError) as caught:
                        job._run_local()
                self.assertIs(caught.exception, primary)
                for stream in streams:
                    stream.close.assert_called_once_with()
                self.assertTrue(any('close denied' in note for note in primary.__notes__))

    def test_cleanup_only_failure_reports_all_stream_errors(self):
        job = object.__new__(CommandJob)
        job._argv, job._env, job._reason, job._input = ['true'], None, None, b'x'
        failures = [OSError('stdin failed'), OSError('stdout failed'), OSError('stderr failed')]
        streams = [Mock(close=Mock(side_effect=error)) for error in failures]
        process = Mock(poll=Mock(return_value=0), wait=Mock(return_value=0),
                       stdin=streams[0], stdout=streams[1], stderr=streams[2])
        selector = MagicMock()
        selector.__enter__.return_value.get_map.return_value = {}
        with patch('commandjob.subprocess.Popen', return_value=process), \
             patch('commandjob.os.set_blocking'), \
             patch('commandjob.selectors.DefaultSelector', return_value=selector):
            with self.assertRaises(OSError) as caught:
                job._run_local()
        self.assertIs(caught.exception, failures[0])
        self.assertEqual(job._status, 0)
        for stream in streams:
            stream.close.assert_called_once_with()
        self.assertTrue(any('stdout failed' in note for note in caught.exception.__notes__))
        self.assertTrue(any('stderr failed' in note for note in caught.exception.__notes__))

    def test_reap_and_stream_cleanup_continue_after_signal_failure(self):
        job = object.__new__(CommandJob)
        primary = RuntimeError('command failed')
        signal_error = PermissionError('signal denied')
        wait_error = OSError('wait denied')
        job._signal = Mock(side_effect=signal_error)
        streams = [Mock() for _ in range(3)]
        process = Mock(poll=Mock(return_value=None), wait=Mock(side_effect=wait_error),
                       stdin=streams[0], stdout=streams[1], stderr=streams[2])
        job._cleanup_local(process, primary)
        process.wait.assert_called_once_with(timeout=1)
        for stream in streams:
            stream.close.assert_called_once_with()
        self.assertTrue(any('signal denied' in note for note in primary.__notes__))
        self.assertTrue(any('wait denied' in note for note in primary.__notes__))

    def test_timeout_reports_worker_and_cleanup_failures_without_changing_type(self):
        from commandjob import JobResult
        job = object.__new__(CommandJob)
        job._done = threading.Event()
        job._done.set()
        job.timeout = .1
        job._result = JobResult('', '', None, 'localhost', .2, 'sleep', 'timeout', 'unknown')
        failure = PermissionError('signal denied')
        failure.add_note('Local job cleanup failed during stdout.close(): close denied')
        job._error = failure
        with self.assertRaises(CommandTimeoutError) as caught:
            job.wait()
        self.assertIs(caught.exception.__cause__, failure)
        self.assertTrue(any('close denied' in note for note in caught.exception.__notes__))
        self.assertEqual(caught.exception.termination_status, 'unknown')

    def test_legacy_error_waits_for_command_worker_cleanup(self):
        from dollar import Dollar
        import asyncio
        session = self.local()
        cleanup_started, release_cleanup, caller_done = (threading.Event() for _ in range(3))
        failure = TimeoutError('worker timed out')
        observed = []
        async def fail(execution, get_pty=None):
            execution.channel = Mock(closed=True)
            raise failure
        async def delayed_cleanup(loop):
            cleanup_started.set()
            if not release_cleanup.wait(2):
                raise RuntimeError('test cleanup barrier was not released')
        def invoke():
            try:
                session(['true'])
            except BaseException as exc:
                observed.append(exc)
            finally:
                caller_done.set()
        with patch.object(Dollar, 'async_call_worker', fail), \
             patch.object(asyncio.BaseEventLoop, 'shutdown_default_executor', delayed_cleanup):
            caller = threading.Thread(target=invoke)
            caller.start()
            try:
                self.assertTrue(cleanup_started.wait(2))
                self.assertFalse(caller_done.wait(.1), 'returned before worker cleanup completed')
            finally:
                release_cleanup.set()
                caller.join(3)
        self.assertFalse(caller.is_alive())
        self.assertEqual(observed, [failure])
        self.assertFalse(session.dollar.call_thread.is_alive())

    def test_force_stop_does_not_send_later_sigint_to_dying_group(self):
        job = object.__new__(CommandJob)
        job._process = Mock(pid=123, poll=Mock(return_value=None))
        job._channel = None
        job._signal_lock = threading.Lock()
        job._sent_local_signals = set()
        with patch('commandjob.os.killpg', side_effect=[None, PermissionError]) as killpg:
            job._signal(force=True)
            job._signal()
            job._signal(force=True)
        killpg.assert_called_once_with(123, signal.SIGKILL)
        self.assertEqual(job._sent_local_signals, {signal.SIGKILL})

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
