"""Managed one-shot commands with bounded capture, cancellation and deadlines.

SSH cancellation owns a channel, never the shared transport. Closing a channel
is not proof that its remote process (or descendants) has terminated.
"""
import codecs
from collections import deque
from dataclasses import dataclass
import math
import os
import selectors
import shlex
import signal
import sys
import subprocess
import threading
import time

if __package__:
    from .commandresult import CommandResult
else:
    from commandresult import CommandResult


@dataclass(frozen=True)
class JobResult(CommandResult[int | None]):
    """Captured tails of a managed command; None means no exit status observed."""
    exitcode: int | None
    stop_reason: str = 'completed'
    termination_status: str = 'confirmed'
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class CommandTimeoutError(TimeoutError):
    """A command budget expired, after bounded cancellation and cleanup."""
    def __init__(self, result, timeout):
        super().__init__(f'command exceeded its {timeout:g}s time budget')
        self.result = result
        self.command = result.command
        self.host = result.host
        self.timeout = timeout
        self.elapsed = result.duration
        self.stdout = result.stdout
        self.stderr = result.stderr
        self.termination_status = result.termination_status


def _seconds(value, name, allow_none=True):
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f'{name} must be a finite positive number' + (' or None' if allow_none else ''))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be finite and greater than zero')


class CommandJob:
    """Owned command. Use Session.start(), wait(), stop(), and a with block.

    iter_stdout() yields UTF-8 text chunks (not necessarily complete lines).
    Capture retains at most capture_limit bytes per stream. The streaming queue
    retains 128 chunks; a slow consumer gets BufferError rather than silent loss.
    wait()/stop() are repeatable. stop() requests SIGINT locally, or Ctrl-C on a
    remote PTY, then allows stop_timeout seconds before forced cleanup.
    """
    def __init__(self, session, execution, *, timeout=None, stop_timeout=3,
                 capture_limit=1024 * 1024, check=False, input=None, env=None,
                 get_pty=False):
        _seconds(timeout, 'timeout')
        _seconds(stop_timeout, 'stop_timeout', False)
        if isinstance(capture_limit, bool) or not isinstance(capture_limit, int):
            raise TypeError('capture_limit must be an integer')
        if capture_limit < 0:
            raise ValueError('capture_limit must be nonnegative')
        if not isinstance(check, bool) or not isinstance(get_pty, bool):
            raise TypeError('check and get_pty must be bool')
        if get_pty and session._client is None:
            raise ValueError('managed local jobs do not support get_pty; use Session.enter()')
        if input is not None and not isinstance(input, (str, bytes)):
            raise TypeError('input must be str, bytes or None')
        if env is not None:
            if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
                raise TypeError('env must map strings to strings')
            if any(not k or '\x00' in k + v or '=' in k for k, v in env.items()):
                raise ValueError('env contains an invalid name or value')
        self._session = session  # Keep the transport owner alive for this job.
        self.settings = session.get()
        self.logger = execution.logger
        self.command = execution.argv or execution.command
        self.host = session.host
        self._client = session._client
        self._argv = ([execution.shell_executable or '/bin/sh', '-c', execution.command]
                      if execution.use_shell else list(execution.argv or shlex.split(execution.command)))
        self.timeout = timeout
        self.stop_timeout = stop_timeout
        self.capture_limit = capture_limit
        self.check = check
        self._input = input.encode('utf-8') if isinstance(input, str) else (input or b'')
        self._env = env
        self._pty = get_pty
        self._condition = threading.Condition()
        self._tails = [bytearray(), bytearray()]
        self._truncated = [False, False]
        self._chunks = deque(maxlen=128)
        self.dropped_stdout_chunks = 0
        self._signal_lock = threading.Lock()
        self._sent_local_signals = set()
        self._process = self._channel = None
        self._status = None
        self._error = None
        self._reason = None
        self._cancelled_at = None
        self._worker_done = threading.Event()
        self._done = threading.Event()
        self._result = None
        self._started = time.monotonic()
        self._deadline = None if timeout is None else self._started + timeout
        self._worker = threading.Thread(target=self._run, name='sshscript-command-io', daemon=True)
        self._monitor = threading.Thread(target=self._watch, name='sshscript-command-watch', daemon=True)

    def _launch(self):
        self._worker.start()
        self._monitor.start()
        return self

    @property
    def done(self):
        return self._done.is_set()

    @property
    def stdout(self):
        with self._condition:
            return bytes(self._tails[0]).decode('utf-8', errors='replace')

    @property
    def stderr(self):
        with self._condition:
            return bytes(self._tails[1]).decode('utf-8', errors='replace')

    @property
    def exitcode(self):
        return self._result.exitcode if self.done else self._status

    def clear(self):
        """Clear live captured tails; previously returned snapshots stay valid."""
        with self._condition:
            for tail in self._tails:
                tail.clear()

    def _capture(self, stream, data):
        if self.settings['verbose'] or (stream == 1 and self.settings['verbose_stderr']):
            target = sys.stdout if stream == 0 else sys.stderr
            target.write(data.decode('utf-8', errors='replace'))
            target.flush()
        with self._condition:
            if self.done:
                return
            tail = self._tails[stream]
            tail.extend(data)
            if len(tail) > self.capture_limit:
                self._truncated[stream] = True
                del tail[:len(tail) - self.capture_limit]
            if stream == 0:
                if len(self._chunks) == self._chunks.maxlen:
                    self.dropped_stdout_chunks += 1
                self._chunks.append(data)
            self._condition.notify_all()

    def _request_stop(self, reason):
        with self._condition:
            if not self.done and not self._worker_done.is_set() and self._reason is None:
                now = time.monotonic()
                self._reason = 'timeout' if self._deadline is not None and now >= self._deadline else reason
                self._cancelled_at = now
                self._condition.notify_all()

    def _signal(self, force=False):
        process, channel = self._process, self._channel
        if process is not None:
            # Own process group includes ordinary shell pipelines/descendants.
            # Descendants which create a new session are outside this guarantee.
            sig = signal.SIGKILL if force else signal.SIGINT
            with self._signal_lock:
                if sig not in self._sent_local_signals:
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        # The worker may have already reaped the group leader
                        # while the watcher was sending its final signal. Only
                        # accept that race when child exit is actually confirmed.
                        if process.poll() is None:
                            raise
                    self._sent_local_signals.add(sig)
        if channel is not None:
            if force or not self._pty:
                channel.close()
            elif channel.send_ready():
                channel.send(b'\x03')

    def _watch(self):
        signalled_resource = None
        while not self._worker_done.wait(0.02):
            now = time.monotonic()
            if self._deadline is not None and now >= self._deadline:
                self._request_stop('timeout')
            if self._reason is not None:
                resource = self._process if self._process is not None else self._channel
                try:
                    if resource is not None and resource is not signalled_resource:
                        self._signal()
                        signalled_resource = resource
                    if now >= self._cancelled_at + self.stop_timeout:
                        self._signal(force=True)
                        if self._worker_done.wait(1):
                            break
                        # Never wait indefinitely for a broken backend to close.
                        break
                except Exception as exc:
                    self._error = exc
                    try:
                        self._signal(force=True)
                    except Exception:
                        pass
                    self._worker_done.wait(1)
                    break
        with self._condition:
            status = self._status
            self._result = JobResult(
                self.stdout, self.stderr, status, self.host,
                time.monotonic() - self._started, self.command,
                self._reason or 'completed',
                'confirmed' if status is not None else 'unknown',
                *self._truncated,
            )
            self._done.set()
            self._condition.notify_all()

    def _run(self):
        self.logger.debug('Starting managed command (host=%s)', self.host)
        try:
            if self._client is None:
                self._run_local()
            else:
                self._run_remote()
        except Exception as exc:
            if self._reason is None or self._client is None:
                self._error = exc
        finally:
            try:
                if self._channel is not None:
                    self._channel.close()
            except Exception as exc:
                if self._error is None:
                    self._error = exc
            finally:
                if self._deadline is not None and time.monotonic() >= self._deadline:
                    self._request_stop('timeout')
                self._worker_done.set()

    def _run_local(self):
        process = subprocess.Popen(self._argv, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=None if self._env is None else dict(os.environ, **self._env),
                                   start_new_session=True)
        self._process = process
        try:
            # Cancellation may have arrived while Popen was creating the process.
            if self._reason is not None:
                self._signal(force=True)
            with selectors.DefaultSelector() as selector:
                for index, stream in enumerate((process.stdout, process.stderr)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, index)
                pending = memoryview(self._input)
                if pending:
                    os.set_blocking(process.stdin.fileno(), False)
                    selector.register(process.stdin, selectors.EVENT_WRITE, 2)
                else:
                    process.stdin.close()
                while selector.get_map():
                    for key, _ in selector.select(0.02):
                        if key.data == 2:
                            try:
                                pending = pending[os.write(key.fd, pending[:8192]):]
                            except BrokenPipeError:
                                pending = pending[:0]
                            except BlockingIOError:
                                continue
                            if not pending:
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                        else:
                            try:
                                data = os.read(key.fd, 8192)
                            except BlockingIOError:
                                continue
                            if data:
                                self._capture(key.data, data)
                            else:
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                    if self._reason is not None and time.monotonic() >= self._cancelled_at + self.stop_timeout:
                        self._signal(force=True)
                        break
                while process.poll() is None:
                    if self._reason is not None and time.monotonic() >= self._cancelled_at + self.stop_timeout:
                        self._signal(force=True)
                        break
                    time.sleep(0.02)
                self._status = process.wait(timeout=1)
        finally:
            if process.poll() is None:
                self._signal(force=True)
                try:
                    self._status = process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()

    def _run_remote(self):
        remaining = None if self._deadline is None else max(0.001, self._deadline - time.monotonic())
        channel = self._client.get_transport().open_session(timeout=remaining)
        self._channel = channel
        if self._reason is not None:
            channel.close()
            return
        if self._pty:
            channel.get_pty()
        if self._env:
            channel.update_environment(self._env)
        channel.exec_command('exec ' + shlex.join(self._argv))
        channel.settimeout(0.0)
        pending = memoryview(self._input)
        eof_sent = False
        while True:
            made_progress = False
            # Read only one bounded chunk per stream per turn: a busy stdout
            # must not starve stderr, stdin, completion or cancellation.
            for index, ready, read in ((0, channel.recv_ready, channel.recv),
                                      (1, channel.recv_stderr_ready, channel.recv_stderr)):
                if ready():
                    data = read(8192)
                    if data:
                        self._capture(index, data)
                        made_progress = True
            if pending and channel.send_ready():
                sent = channel.send(pending[:8192].tobytes())
                if sent == 0:
                    raise BrokenPipeError('SSH stdin closed before input was sent')
                pending = pending[sent:]
            if not pending and not eof_sent:
                # Keep PTY input open so stop() can send Ctrl-C.
                if not self._pty:
                    channel.shutdown_write()
                eof_sent = True
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready() and (channel.eof_received or channel.closed):
                status = channel.recv_exit_status()
                self._status = None if status == -1 else status
                if self._status is None and self._reason is None:
                    raise EOFError('SSH channel closed without an exit status')
                return
            if channel.closed and not channel.recv_ready() and not channel.recv_stderr_ready():
                if self._reason is None:
                    raise EOFError('SSH channel closed before command completion')
                return
            if not made_progress:
                time.sleep(0.01)

    def wait(self):
        """Wait for completion. The job's deadline continues while nobody waits."""
        self._done.wait()
        if self._result.stop_reason == 'timeout':
            raise CommandTimeoutError(self._result, self.timeout)
        if self._error is not None:
            raise self._error
        if self.check and self._result.stop_reason == 'completed' and self._result.exitcode != 0:
            error = subprocess.CalledProcessError(self._result.exitcode, self.command,
                                                 output=self._result.stdout, stderr=self._result.stderr)
            error.result = self._result
            raise error
        return self._result

    def stop(self):
        """Request user cancellation, finish bounded cleanup, return JobResult.

        An unconfirmed remote stop is returned as termination_status='unknown'.
        An earlier deadline still raises CommandTimeoutError.
        """
        self._request_stop('cancelled')
        return self.wait()

    def iter_stdout(self):
        """Yield decoded text chunks; fail explicitly if the consumer falls behind."""
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._chunks or self.done)
                if self.dropped_stdout_chunks:
                    raise BufferError('stdout consumer fell behind; use faster streaming or redirect output at the source')
                data = self._chunks.popleft() if self._chunks else None
                if data is None and self.done:
                    break
            text = decoder.decode(data)
            if text:
                yield text
        text = decoder.decode(b'', final=True)
        if text:
            yield text
        self.wait()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.stop() if not self.done else self.wait()
        except Exception as exc:
            if exc_value is None:
                raise
            if exc is not exc_value and not (
                isinstance(exc, CommandTimeoutError)
                and isinstance(exc_value, CommandTimeoutError)
                and exc.result is exc_value.result
            ):
                exc_value.add_note(f'command cleanup also raised {type(exc).__name__}')
        return False
