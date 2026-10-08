"""Single foreground jobs on an existing Bash console; no channel ownership transfer."""
import os
import codecs
import shlex
import threading
import time
import uuid
from types import SimpleNamespace

if __package__:
    from .commandjob import CommandJob, JobResult
else:
    from commandjob import CommandJob, JobResult


def validate_console_command(command):
    if not isinstance(command, str):
        raise TypeError('console.start() requires a command string, not argv')
    if not command.strip() or any(c in command for c in '\x00\r\n'):
        raise ValueError('console.start() requires one nonempty command line')
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens = list(lexer)
    # These are explicit unsupported forms, not a shell sandbox/parser.
    # Preserve quoting: an ampersand argument is data, not background syntax.
    quote = None
    escaped = False
    operators = []
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == '\\' and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == '&':
            before = command[index - 1:index]
            after = command[index + 1:index + 2]
            if before != '&' and after not in ('&', '>') and before not in ('>', '<'):
                operators.append(char)
    if operators:
        raise ValueError('console.start() manages one foreground command; background execution is unsupported')
    head = True
    for token in tokens:
        if token in (';', '&&', '||', '|', '(', '{'):
            head = True
        elif head:
            if '=' in token and not token.startswith('='):
                continue
            if token in ('env', 'command', 'builtin') or token.startswith('-'):
                continue
            if os.path.basename(token) in ('su', 'sudo'):
                raise ValueError('use nested console.su()/sudo() before start(), not a raw privilege command')
            if os.path.basename(token) in ('nohup', 'disown', 'exec'):
                raise ValueError('console.start() cannot manage commands that detach or replace its shell')
            head = False
    return command


class ConsoleCommandJob(CommandJob):
    """CommandJob interface with a creator-thread-only, exclusive console backend."""
    def __init__(self, console, command, *, timeout=60, stop_timeout=3,
                 capture_limit=1024 * 1024, check=False):
        command = validate_console_command(command)
        session = console.channel.owner.session
        execution = SimpleNamespace(logger=session.logger, argv=None, command=command,
                                    use_shell=True, shell_executable=None)
        super().__init__(session, execution, timeout=timeout, stop_timeout=stop_timeout,
                         capture_limit=capture_limit, check=check)
        self.console = console
        self._console_channel = console.channel
        self._creator = threading.get_ident()
        self._token = uuid.uuid4().hex
        self._prefix = '\n__SSJ_' + self._token + '_'
        self._pending = ['', '']
        self._decoders = [codecs.getincrementaldecoder('utf-8')(errors='replace') for _ in range(2)]
        self._prompt = console.channel.prompt
        self._await_prompt = None
        self._records = {}
        self._mode = 'probe'
        self._stream_end = [False, False]
        self._identity = None
        self._recovered = False
        self._sent_command = False
        self._buffers = None
        self._listeners = []
        self._execution_lock = None
        self._old_dump = None

    def _assert_creator(self):
        if threading.get_ident() != self._creator:
            raise RuntimeError('console job operations must run on the thread that called start()')

    def wait(self):
        self._assert_creator()
        try:
            return super().wait()
        except Exception as error:
            if self._result is not None:
                error.result = self._result
            raise

    def stop(self):
        self._assert_creator()
        return super().stop()

    def iter_stdout(self):
        self._assert_creator()
        yield from super().iter_stdout()

    def clear(self):
        self._assert_creator()
        return super().clear()

    def __enter__(self):
        self._assert_creator()
        return self

    def _emit(self, kind, arguments, fmt, stderr=False):
        # No complete marker is present in terminal input/echo.
        return ('printf "\\n%s%s' + fmt + '\\n" "__SSJ_" '
                + shlex.quote(self._token + '_' + kind + '__') + ' ' + arguments
                + (' >&2' if stderr else ''))

    def _probe(self, kind):
        return self._emit(kind, '"$(id -u)" "$$" "${BASH_VERSION-}"', ':%s:%s:%s')

    def _listen(self, index, text):
        pending = self._pending[index] + text
        while pending:
            position = pending.find(self._prefix)
            prompt_position = pending.find(self._prompt) if self._prompt else -1
            if prompt_position >= 0 and (position < 0 or prompt_position < position):
                self._output(index, pending[:prompt_position])
                pending = pending[prompt_position + len(self._prompt):]
                with self._condition:
                    if self._await_prompt is not None:
                        self._records[self._await_prompt + '_PROMPT'] = []
                        self._await_prompt = None
                    self._condition.notify_all()
                continue
            if position >= 0:
                self._output(index, pending[:position - 1] if position and pending[position - 1] == '\r' else pending[:position])
                end = pending.find('\n', position + len(self._prefix))
                if end < 0:
                    pending = pending[position:]
                    if len(pending) > 512:
                        raise RuntimeError('invalid console job protocol record')
                    break
                record = pending[position + len(self._prefix):end].rstrip('\r')
                kind, separator, fields = record.partition('__')
                if not separator or kind not in ('BEGIN', 'DONE', 'END', 'READY'):
                    raise RuntimeError('invalid console job protocol record')
                with self._condition:
                    self._records[kind] = fields.lstrip(':').split(':')
                    if kind in ('BEGIN', 'READY'):
                        self._await_prompt = kind
                    if kind == 'DONE':
                        self._stream_end[0] = True
                    elif kind == 'END':
                        self._stream_end[1] = True
                    elif kind == 'READY':
                        self._mode = 'probe'
                    self._condition.notify_all()
                pending = pending[end + 1:]
            else:
                # Hold only a potential marker prefix, never a whole output line.
                prefixes = (self._prefix, '\r' + self._prefix) + ((self._prompt,) if self._prompt else ())
                keep = min(len(pending), max(map(len, prefixes)) - 1)
                while keep and not any(p.startswith(pending[-keep:]) for p in prefixes):
                    keep -= 1
                self._output(index, pending[:-keep] if keep else pending)
                pending = pending[-keep:] if keep else ''
                break
        self._pending[index] = pending

    def _output(self, index, text):
        if text and self._mode == 'running' and not self._stream_end[index]:
            self._capture(index, text.encode('utf-8'))

    def _await(self, kinds, deadline, cancellable=False):
        while True:
            with self._condition:
                if all(kind in self._records for kind in kinds):
                    return True
            self._console_channel._raise_if_unusable()
            now = time.monotonic()
            if not cancellable and self._reason is not None:
                deadline = min(deadline or float('inf'), self._cancelled_at + self.stop_timeout)
            if cancellable:
                if self._deadline is not None and now >= self._deadline:
                    self._request_stop('timeout')
                if self._reason is not None:
                    return False
            if deadline is not None and now >= deadline:
                raise TimeoutError('console job protocol handshake timed out')
            with self._condition:
                self._condition.wait(0.02)

    def _send(self, text, deadline):
        self._console_channel.send(text + '\n', timeout=max(0.001, deadline - time.monotonic()))

    def _recover(self):
        channel = self._console_channel
        deadline = time.monotonic() + self.stop_timeout
        if self._reason is not None and self._sent_command and 'DONE' not in self._records:
            if not channel.owner.get_pty:
                raise RuntimeError('pipe console cannot interrupt safely; recovery is unconfirmed')
            channel.send('\x03', timeout=max(0.001, deadline - time.monotonic()))
        self._send(self._probe('READY'), deadline)
        self._await(['READY'], deadline)
        if self._prompt:
            self._await(['READY_PROMPT'], deadline)
        if self._records['READY'][:2] != self._identity:
            raise RuntimeError('console job did not return to the original UID and shell PID')
        if not self._records['READY'][2]:
            raise RuntimeError('console.start() requires a Bash console')
        self._recovered = True

    def _run(self):
        channel = self._console_channel
        try:
            lock = channel.executing_lock
            if not lock.acquire(blocking=False):
                raise RuntimeError('console is busy; finish its current operation before start()')
            self._execution_lock = lock
            channel.reset_buffer()
            self._buffers = (channel._stdout, channel._stderr)
            self._old_dump = channel.dump2sys
            channel.dump2sys = (0, 0)  # Forward only filtered user output.
            for index, buffer in enumerate(self._buffers):
                def listener(text, i=index, b=buffer):
                    try:
                        self._listen(i, text)
                    except Exception as exc:
                        self._error = exc
                        channel.fail(exc)
                    finally:
                        # Called with the buffer condition held. Job owns output.
                        b._deque.clear()
                buffer.push_listener(listener)
                self._listeners.append(listener)
            startup = min(self._deadline or float('inf'), time.monotonic() + 10)
            self._send(self._probe('BEGIN'), startup)
            self._await(['BEGIN'], startup)
            if self._prompt:
                self._await(['BEGIN_PROMPT'], startup)
            fields = self._records['BEGIN']
            if len(fields) != 3 or not all(value.isdigit() for value in fields[:2]):
                raise RuntimeError('invalid console shell identity')
            self._identity = fields[:2]
            if not fields[2]:
                raise RuntimeError('console.start() requires Bash; use console.shell("bash")')
            if self._deadline is not None and time.monotonic() >= self._deadline:
                self._request_stop('timeout')
            if self._reason is None:
                self._mode = 'running'
                self._sent_command = True
                trailer = self._emit('DONE', '"$?" "$(id -u)" "$$"', ':%s:%s:%s')
                trailer += '; ' + self._emit('END', '', '', stderr=True)
                self._send('eval -- ' + shlex.quote(self.command) + '; ' + trailer, startup)
                complete = self._await(['DONE', 'END'], None, cancellable=True)
                if complete:
                    fields = self._records['DONE']
                    if len(fields) != 3 or fields[1:] != self._identity:
                        raise RuntimeError('console job completion identity mismatch')
                    self._status = int(fields[0])
                    if self._deadline is not None and time.monotonic() >= self._deadline:
                        self._request_stop('timeout')
            self._recover()
        except Exception as exc:
            if self._deadline is not None and time.monotonic() >= self._deadline:
                self._request_stop('timeout')
            failure = RuntimeError('console job recovery is unconfirmed; create a new console')
            failure.__cause__ = exc
            self._error = failure
            channel.fail(failure)
        finally:
            try:
                if self._buffers is not None:
                    for buffer, listener in zip(self._buffers, self._listeners):
                        buffer.pop_listener(listener)
                    channel.dump2sys = self._old_dump
            except Exception as exc:
                self._error = self._error or exc
                self._recovered = False
                channel.fail(RuntimeError('console job listener cleanup failed; recovery is unconfirmed'))
            finally:
                if self._execution_lock is not None and self._execution_lock.locked():
                    self._execution_lock.release()
                self._worker_done.set()

    def _watch(self):
        self._worker_done.wait()
        with self._console_channel._console_job_lock, self._condition:
            self._result = JobResult(
                self.stdout, self.stderr, self._status, self.host,
                time.monotonic() - self._started, self.command,
                self._reason or 'completed', 'confirmed' if self._recovered else 'unknown',
                *self._truncated,
            )
            if self._console_channel._console_job is self:
                self._console_channel._console_job = None
            self._done.set()
            self._condition.notify_all()
