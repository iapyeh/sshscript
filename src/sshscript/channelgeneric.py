# Copyright (C) 2022-2026  Hsin Yuan Yeh <iapyeh@gmail.com>
#
# This file is part of Sshscript.
#
# SSHScript is free software; you can redistribute it and/or modify it under the
# terms of the MIT License.
#
# SSHScript is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the MIT License for more details.
#
# You should have received a copy of the MIT License along with SSHScript;
# if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA.
#

import threading, os, sys, re
import time
import logging
import paramiko
import asyncio
import concurrent.futures
if __package__:
    from .stdio import DequeString,SSHScriptStdout,SSHScriptStderr
    from .errorutils import get_logger,EXITCODE_DEFAULT,command_summary
else:
    from stdio import DequeString,SSHScriptStdout,SSHScriptStderr
    from errorutils import get_logger,EXITCODE_DEFAULT,command_summary

logger = get_logger()

class GenericChannel(object):
    """Base class for channel implementations.
    
    This class provides common functionality for different channel types,
    handling stdout/stderr buffering, exit code tracking, and I/O operations.
    
    References:
    - VT100 escape sequences: https://stackoverflow.com/questions/7857352/python-regex-to-match-vt100-escape-sequences
    - Win32 non-blocking read: https://stackoverflow.com/questions/34504970/non-blocking-read-on-os-pipe-on-windows
    """
    
    ## ref: https://stackoverflow.com/questions/7857352/python-regex-to-match-vt100-escape-sequences
    ## Win32's ref: https://stackoverflow.com/questions/34504970/non-blocking-read-on-os-pipe-on-windows
    ## fish returns more complex control codes than other shells( "\n" \x0a is excluded from the following pattern)
        
    def __init__(self,owner):
        """Initialize a GenericChannel instance.
        
        :owner: The owner of this channel (typically a Dollar instance)
        """
        self._native_id = str(int(time.time()))
        ## initial exitcode can not be -1,
        ## because it would trigger a calling to get the exitcode
        self._exitcode = None
        self._enter_counter = 0

        ## Guarding self._stdout, self._stderr,self.stdio_store
        self._lock = threading.RLock()
        ##lastOutputTime :最後一次有輸出的時間
        self.lastIOAtTime = [time.time(),time.time()] ## input(send), output(stderr,stdout)

        ## this is for onedollar and twodollar
        # asyncio primitives must be created while their owning loop is
        # running.  Constructing this during a synchronous import/API call can
        # create a process-default loop that is never closed.
        self._dumpCondition = None
        self._dumpBuf = []
        self._stdoutDumpBuf = b''
        self._stderrDumpBuf = b''
        
        ## an instance of Dollar
        self.owner = owner

        ## see hijack() for details
        self.hijacked = False
        self._send_line = None
        
        ## set default value for PopenChannel and SSHChannel
        self.with_pty = None

        ## 確保跟上一個命令之間有間隔的方式：
        ## 執行命令之前(sendcommand)，檢查上一個命令是否有取得exitcode，
        ## 如果沒有，則送出一個dumyEcho
        #self._exitcode_session_id = 0
        #self._command_session_id = 0
        if os.environ.get('VERBOSE'):
            ## verbose-related
            self.dump2sys = (1,1)
            self.stdoutPrefix = os.environ.get('VERBOSE_STDOUT_PREFIX','🟩').encode('utf8')
            self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','🟨').encode('utf8')
        elif os.environ.get('VERBOSE_STDERR'):
            self.dump2sys = (0,1)
            self.stdoutPrefix = b''
            self.stderrPrefix = os.environ.get('VERBOSE_STDERR_PREFIX','🟨').encode('utf8')
        else:
            self.dump2sys = (0,0)
            self.stderrPrefix = b''
            self.stdoutPrefix = b''
        
        self.closed = False
        self.withChannelWrapper = None
        
        ## mostly is $? for bash, sh, zsh, but it is "$status" for fish
        #self._exitcodeSymbol = ('echo','$?')

        ## rotate the command to ask for exitcode, this is for preventing from falsely got previous exitcode
        self._exitcodeSno = 0
        self.exitcodePatterns = []
        for sno in range(10):
            #f'echo "_{sno}_$?_{sno}{sno}_"\n') 
            pat = re.compile(r'(\W?)(?:echo )?_' + str(sno) + r'_(\d+)_' + str(sno) + str(sno) + r'_(?:\r?\n)?',re.M)
            self.exitcodePatterns.append(pat)

        ## layer's variable
        self.executing_locks = []
        self.prompts= []
        self.stdio_store = []
        self._exited_interactive_layers = set()

        self.prefixOfLog = '[Channel]'

        
        #self.sending_queue = asyncio.Queue()
        #self._sending_error = None

        ## initailly set layer 1
        self.increase_layer('')
        ## this flag control $.shell to use existing layer or increase layer
        self.on_generic_layer = True 

        #self.interaction_thread = None

        ## for self.expect()
        self._expect_lock = threading.RLock()       
        

        ## related to channel's lifecycle (suggested by codex)
        #self._state_lock = threading.RLock()
        self._state = 'starting'
        self._failure = None
        self._interaction_ready = threading.Event()
        self._interaction_stopped = threading.Event()
        # 不再使用 asyncio.Queue。
        self._send_call_lock = threading.Lock()
        self._async_send_lock = None
        self.send_timeout = 30
        self.command_timeout = 60         

    @property
    def executing_lock(self):
        return self.executing_locks[-1]
    @property
    def prompt(self):
        return self.prompts[-1]
    @prompt.setter
    def prompt(self,text):
        self.prompts[-1] = text
    @property
    def _stdout(self):
        return self.stdio_store[-1][0]            
    @property
    def _stderr(self):
        return self.stdio_store[-1][1]
    @property
    def layer_count(self):
        return len(self.stdio_store)

    def _interactive_layer_exited(self, layer_lock):
        with self._lock:
            return layer_lock in self._exited_interactive_layers

    def _mark_interactive_layer_exited(self, layer_lock):
        with self._lock:
            self._exited_interactive_layers.add(layer_lock)
    
    def increase_layer(self,prompt):
        ## clone the current _stdout, stderr
        ## there are the message of shell, su or sudo, and important
        ## there also having "password:" prompt, it would be the targets for expect()
        with self._lock:
            if len(self.stdio_store):
                self.stdio_store.append((SSHScriptStdout(self._stdout),SSHScriptStderr(self._stderr)))
            else:
                self.stdio_store.append((SSHScriptStdout(),SSHScriptStderr()))
            self.prompts.append(prompt)
            self.executing_locks.append(threading.Lock())
    def decrease_layer(self):
        ## keep at least one layer
        assert self.layer_count > 1
        with self._lock:
            self.prompts.pop()
            layer_lock = self.executing_locks.pop()
            self._exited_interactive_layers.discard(layer_lock)
            self.stdio_store.pop()
    

    ## lifecycle related helpers (by codex)
    def _set_open(self):
        with self._lock:
            if self._state == 'starting':
                self._state = 'open'
            self._interaction_ready.set()
    def fail(self, exc):
        """Mark the channel unusable and wake all synchronous waiters."""
        if not isinstance(exc, BaseException):
            exc = RuntimeError(str(exc))

        with self._lock:
            if self._state in ('closing', 'closed'):
                return

            if self._failure is None:
                self._failure = exc

            self._state = 'failed'
            self._interaction_ready.set()
    def _raise_if_unusable(self):
        with self._lock:
            failure = self._failure
            state = self._state

        if failure is not None:
            raise failure

        if state != 'open':
            raise BrokenPipeError(
                f'channel is not open (state={state})'
            )
    def _begin_close(self):
        with self._lock:
            if self._state in ('closing', 'closed'):
                return False

            self._state = 'closing'
            self._interaction_ready.set()
            return True
    def _finish_close(self):
        with self._lock:
            self._state = 'closed'
            self.closed = True
            self._interaction_ready.set()
            # 順便避免先前發現的多層 stdio FD leak。
            for stdout, stderr in tuple(self.stdio_store):
                if not stdout.closed:
                    stdout.close()
                if not stderr.closed:
                    stderr.close()    


    def _increase_exitcode_sno(self):
        """Increment the exit code sequence number.
        
        :return: The new sequence number (0-29)
        """
        self._exitcodeSno = (self._exitcodeSno + 1) % 10
        return self._exitcodeSno

    @property
    def is_su_pty_ok(self):
        return self.owner.session.is_su_pty_ok
    @property
    def os_name(self):
        return self.owner.session.os_name
    
    @property
    def lastOutputTime(self):
        """Get the timestamp of the last output.
        
        :return: Timestamp of the last output
        """
        return self.lastIOAtTime[1]
    
    
    def touchIO(self,isOutput):
        """Update the I/O timestamps.
        
        :isOutput: True if this is an output operation, False for input
        """
        if isOutput:
            self.lastIOAtTime[1] = time.time()
        else:
            ## sending command, also reset output time
            self.lastIOAtTime[0] = self.lastIOAtTime[1] = time.time()

    ## v2.0.3 redefined
    def wait_for_output(self,timeout=0,silent=False)->bool:
        """Block execution until stdout or stderr received or timeout reached.
        
        :timeout: (int)
            0: waiting forever
        :silent: (bool)
            if True, return False when timeout reached
        :return:
            True: has output
            False: timeout(silent=True)
        :raise:
            TimeoutError: timeout(silent=False)
        """
        basetime = self.lastIOAtTime[:]
        timeouttime = (time.time() + timeout) if timeout else 0
        ret = True
        logger.debug(
            '%s Waiting for channel output (timeout=%s, silent=%s)',
            self.prefixOfLog,
            timeout or None,
            silent,
        )
        while True:
            time.sleep(0.2)

            ## check channel state and failure before waiting for notifications
            with self._lock:
                failure = self._failure
                state = self._state

            if self.lastIOAtTime[0] != basetime[0] or \
                self.lastIOAtTime[1] != basetime[1]:
                break
            elif failure is not None:
                raise failure            
            elif state in ('closing', 'closed'):
                raise EOFError('channel closed while waiting for output')                
            elif timeouttime and time.time() > timeouttime:
                if silent:
                    ret = False
                    break
                else:
                    raise TimeoutError(f'wait_for_output exceeded {timeout}')

        logger.debug(
            '%s Channel output wait completed (received=%s)',
            self.prefixOfLog,
            ret,
        )
        return ret
    ## v2.0.3 redefined
    def wait_for_silent(self,seconds,max_seconds=0)->bool:
        """Block execution until output is silent for the specified duration.
        
        If output continues (e.g., from tcpdump), it will block until output stops.
        
        :seconds: (int)
            Wait this many seconds after the last output before returning
        :max_seconds: (int)
            If specified, will raise TimeoutError if output continues for this long
        """
        timeouttime = (time.time() + max_seconds) if max_seconds else 0
        while True:
            now = time.time()
            if now - self.lastIOAtTime[0] >= seconds and\
               now - self.lastIOAtTime[1] >= seconds:
                break
            if timeouttime and now > timeouttime:
                raise TimeoutError(f'wait_for_silent exceeded {max_seconds}')
            time.sleep(0.05)

    ## v3.0
    def wait_for_prompt(self,prompt,timeout=None)->bool:
        """Block execution until output is silent for the specified duration.
        
        If output continues (e.g., from tcpdump), it will block until output stops.
        
        :seconds: (int)
            Wait this many seconds after the last output before returning
        """
        self.expect(prompt,timeout=timeout)

    @property
    def stdout(self)->str:
        """Get the stdout buffer contents.
        
        If not hijacked, ensures exit code is retrieved before returning.
        
        :return: Contents of stdout buffer
        """
        if self.hijacked:
            with self.executing_lock:
                with self._lock:
                    return self._stdout
        else:    
            ## by getting exitcode, make sure we have got all the output of stdout and stderr
            #if self._exitcode == EXITCODE_DEFAULT: self.get_exit_code()
            with self.executing_lock:
                with self._lock:
                    return self._stdout


    @property
    def stderr(self)->str:
        """Get the stderr buffer contents.
        
        If not hijacked, ensures exit code is retrieved before returning.
        
        :return: Contents of stderr buffer
        """
        if self.hijacked:
            with self.executing_lock:
                return self._stderr
        else:
            ## by getting exitcode, make sure we have got all the output of stdout and stderr
            #if self._exitcode == EXITCODE_DEFAULT: self.get_exit_code(1)
            with self.executing_lock:
                return self._stderr

    def hijack(self,yes):
        """
        Called by EnterConsole.       
        Hijack or release the channel's send_line method.
        
        When hijacked
        1. send_line is replaced with input method.
        2. no exitcode 
        
        :yes: True to hijack, False to release
        """
        if yes:
            assert not self.hijacked,'can not hijack twice'
            assert self._send_line is None, 'can not hijack twice'
            with self._lock:
                self._exited_interactive_layers.discard(
                    self.executing_lock
                )
            self._send_line = self.send_line
            self.hijacked = True
            self.send_line = self.input
            return True
        else:
            assert self.hijacked,'can not release hijack twice'
            assert self._send_line is not None, 'should release before hijacking'
            self.send_line = self._send_line
            self._send_line = None
            self.hijacked = False
            return True
        return False

    @property
    def exitcode(self)->int:
        """Get the exit code of the last command.
        
        If exit code is -1, it will be retrieved before returning.
        
        :return: Exit code of the last command
        """
        if self.hijacked:
            #raise ValueError('exitcode is not available in current state')
            logger.warning(
                '%s Exit status is unavailable while the channel is in interactive mode',
                self.prefixOfLog,
            )
            return -1
        ## v2.0.3 request by demamd
        if self._exitcode == EXITCODE_DEFAULT:
            return self.get_exit_code()
        else:
            return self._exitcode

    def log(self,msg, *args, level=logging.DEBUG, **kwargs):
        """Log a message with channel context.
        
        :msg: Message to log
        :*args: Additional arguments for formatting
        :level: Standard logging level; defaults to DEBUG
        :**kwargs: Additional keyword arguments passed to the logger
        """
        if isinstance(level, int) and 0 < level < logging.DEBUG:
            level = logging.DEBUG
        logger.log(level, f'{self.prefixOfLog} {msg}', *args, **kwargs)

    def expect(
        self,
        rawpat,
        timeout=None,
        stdout=True,
        stderr=True,
        silent=False,
    ):
        """Wait until unconsumed stdout or stderr matches a pattern.

        ``rawpat`` may be a str, a str-based compiled regular expression,
        a callable accepting an unconsumed/newly appended str, a list/tuple
        containing those forms, or a dict mapping patterns to response strings.

        Return a regex match, the successful callable, a dict mapping each
        dialog pattern to its match, or None after a silent timeout.
        """
        if not stdout and not stderr:
            raise ValueError("stdout and stderr cannot both be False")

        if timeout in (None, 0):
            timeout = None
        elif not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a number or None")
        elif timeout < 0:
            raise ValueError("timeout cannot be negative")
        else:
            timeout = float(timeout)
            if not 0 < timeout < float("inf"):
                raise ValueError("timeout must be finite")

        def compile_matcher(pattern, allow_callable=True):
            if isinstance(pattern, str):
                return "regex", pattern, re.compile(pattern, re.I)

            if isinstance(pattern, re.Pattern):
                if not isinstance(pattern.pattern, str):
                    raise TypeError(
                        "bytes regular expressions are not supported"
                    )
                return "regex", pattern, pattern

            if allow_callable and callable(pattern):
                return "callback", pattern, pattern

            raise TypeError(
                "pattern must be str, a str-based re.Pattern, or callable"
            )

        dialog_mode = isinstance(rawpat, dict)

        if dialog_mode:
            if not rawpat:
                return {}

            dialog_entries = []

            for pattern, response in rawpat.items():
                if not isinstance(response, str):
                    raise TypeError(
                        "dict response values must be strings"
                    )

                _, original, matcher = compile_matcher(
                    pattern,
                    allow_callable=False,
                )
                dialog_entries.append(
                    [original, matcher, response]
                )

            matchers = None
            timeout_target = list(rawpat)

        else:
            patterns = (
                rawpat
                if isinstance(rawpat, (list, tuple))
                else [rawpat]
            )

            if not patterns:
                raise ValueError("pattern list cannot be empty")

            matchers = [
                compile_matcher(pattern)
                for pattern in patterns
            ]
            dialog_entries = None
            timeout_target = rawpat

        deadline = (
            None
            if timeout is None
            else time.monotonic() + timeout
        )

        caller_id = threading.get_ident()

        if getattr(self, "_expect_owner", None) == caller_id:
            raise RuntimeError(
                "expect() cannot be called recursively"
            )

        if deadline is None:
            acquired = self._expect_lock.acquire()
        else:
            remaining = deadline - time.monotonic()
            acquired = (
                remaining > 0
                and self._expect_lock.acquire(
                    timeout=remaining
                )
            )

        if not acquired:
            if silent:
                return None
            raise TimeoutError(
                f"Not found: {timeout_target!r}"
            )

        self._expect_owner = caller_id
        registrations = []

        try:
            targets = []

            if stdout:
                targets.append(
                    ("stdout", self._stdout)
                )

            if stderr:
                targets.append(
                    ("stderr", self._stderr)
                )

            buffers = dict(targets)
            cursor_attr = "_sshscript_expect_cursor"

            has_callbacks = (
                not dialog_mode
                and any(
                    kind == "callback"
                    for kind, _, _ in matchers
                )
            )

            notification_condition = threading.Condition()
            pending = []
            latest = {}
            listener_errors = []

            def valid_cursor(buffer, text, state):
                return (
                    isinstance(state, dict)
                    and state.get("session_id")
                    == buffer.sessionId
                    and isinstance(
                        state.get("consumed_prefix"),
                        str,
                    )
                    and text.startswith(
                        state["consumed_prefix"]
                    )
                )

            def search_window(stream_name, buffer):
                text = str(buffer)
                state = getattr(
                    buffer,
                    cursor_attr,
                    None,
                )

                if valid_cursor(buffer, text, state):
                    return (
                        text,
                        len(state["consumed_prefix"]),
                    )

                consumed_prefix = ""
                stream_index = (
                    0 if stream_name == "stdout" else 1
                )

                # increase_layer() clones the parent buffers.
                # Inherit the parent's consumed cursor.
                if (
                    len(self.stdio_store) > 1
                    and buffer
                    is self.stdio_store[-1][stream_index]
                ):
                    parent = self.stdio_store[-2][
                        stream_index
                    ]
                    parent_text = str(parent)
                    parent_state = getattr(
                        parent,
                        cursor_attr,
                        None,
                    )

                    if (
                        valid_cursor(
                            parent,
                            parent_text,
                            parent_state,
                        )
                        and text.startswith(parent_text)
                    ):
                        consumed_prefix = parent_state[
                            "consumed_prefix"
                        ]

                setattr(
                    buffer,
                    cursor_attr,
                    {
                        "session_id": buffer.sessionId,
                        "consumed_prefix":
                            consumed_prefix,
                    },
                )

                return text, len(consumed_prefix)

            def commit_cursor(buffer, text, end):
                setattr(
                    buffer,
                    cursor_attr,
                    {
                        "session_id": buffer.sessionId,
                        "consumed_prefix": text[:end],
                    },
                )

            def make_listener(stream_name):
                initial = True
                observed_end = 0

                def listener(item):
                    nonlocal initial, observed_end

                    # Avoid contending for the notification
                    # condition after the deadline.
                    if (
                        deadline is not None
                        and time.monotonic() > deadline
                    ):
                        return

                    with notification_condition:
                        arrived_at = time.monotonic()

                        if (
                            deadline is not None
                            and arrived_at > deadline
                        ):
                            return

                        if not isinstance(item, str):
                            listener_errors.append(
                                (
                                    arrived_at,
                                    TypeError(
                                        "listener payload "
                                        "must be str"
                                    ),
                                )
                            )
                            notification_condition.notify()
                            return

                        is_initial = initial
                        initial = False

                        if is_initial:
                            observed_end = len(item)
                        else:
                            observed_end += len(item)

                        event = (
                            arrived_at,
                            stream_name,
                            is_initial,
                            item,
                            observed_end,
                        )

                        if has_callbacks:
                            # Callables must receive every
                            # appended item.
                            pending.append(event)
                        else:
                            # Regex matching searches the
                            # accumulated buffer, so only the
                            # newest boundary is required.
                            latest[stream_name] = event

                        notification_condition.notify()

                return listener

            def take_notifications():
                if has_callbacks:
                    batch = pending[:]
                    pending.clear()
                else:
                    batch = list(latest.values())
                    latest.clear()

                errors = listener_errors[:]
                listener_errors.clear()

                return batch, errors

            # push_listener() first supplies the current
            # complete snapshot, then registers the listener.
            for stream_name, buffer in targets:
                listener = make_listener(stream_name)
                buffer.push_listener(listener)
                registrations.append(
                    (buffer, listener)
                )

            result = {} if dialog_mode else None
            dialog_prompt_matcher = None
            dialog_prompt_starts = {}

            while True:
                
                expired = (
                    deadline is not None
                    and time.monotonic() >= deadline
                )
                ## check channel state and failure before waiting for notifications
                with self._lock:
                    failure = self._failure
                    state = self._state

                terminal = (
                    "closed"
                    if (self.closed or state in ('closing','closed'))
                    else "timeout"
                    if expired
                    else None
                )

                if terminal is not None:
                    # This condition is the arrival boundary.
                    # Only notifications queued before the
                    # deadline remain eligible.
                    with notification_condition:
                        batch, errors = (
                            take_notifications()
                        )

                else:
                    wait_time = (
                        0.1
                        if deadline is None
                        else min(
                            0.1,
                            max(
                                0.0,
                                deadline
                                - time.monotonic(),
                            ),
                        )
                    )

                    with notification_condition:
                        if (
                            not pending
                            and not latest
                            and not listener_errors
                        ):
                            notification_condition.wait(
                                wait_time
                            )

                        batch, errors = (
                            take_notifications()
                        )

                if deadline is not None:
                    batch = [
                        event
                        for event in batch
                        if event[0] <= deadline
                    ]
                    errors = [
                        error
                        for error in errors
                        if error[0] <= deadline
                    ]

                if errors:
                    raise errors[0][1]

                for (
                    _,
                    stream_name,
                    is_initial,
                    item,
                    observed_end,
                ) in batch:
                    buffer = buffers[stream_name]

                    searchable, search_pos = (
                        search_window(
                            stream_name,
                            buffer,
                        )
                    )

                    # Do not let an earlier notification
                    # search output which arrived afterward.
                    search_end = min(
                        observed_end,
                        len(searchable),
                    )

                    if dialog_mode:
                        if dialog_prompt_matcher is not None:
                            prompt_match = dialog_prompt_matcher.search(
                                searchable,
                                max(
                                    search_pos,
                                    dialog_prompt_starts.get(
                                        stream_name,
                                        0,
                                    ),
                                ),
                                search_end,
                            )

                            if prompt_match is not None:
                                commit_cursor(
                                    buffer,
                                    searchable,
                                    prompt_match.end(),
                                )
                                return result

                            continue

                        matches = []
                        matched_end = None

                        for entry in dialog_entries:
                            (
                                original,
                                matcher,
                                response,
                            ) = entry

                            match = matcher.search(
                                searchable,
                                search_pos,
                                search_end,
                            )

                            if match is None:
                                continue

                            matches.append(
                                (
                                    entry,
                                    original,
                                    match,
                                    response,
                                )
                            )

                            matched_end = max(
                                matched_end
                                or match.end(),
                                match.end(),
                            )

                        if matches:
                            commit_cursor(
                                buffer,
                                searchable,
                                matched_end,
                            )

                            for (
                                entry,
                                original,
                                match,
                                _,
                            ) in matches:
                                result[original] = match
                                dialog_entries.remove(entry)

                            wait_for_prompt = (
                                not dialog_entries
                                and bool(self.prompt)
                            )

                            if wait_for_prompt:
                                # Only accept a prompt emitted after the final
                                # dialog response.  This prevents a previous
                                # prompt in either stream from making password
                                # authentication appear complete too early.
                                dialog_prompt_starts = {
                                    name: len(str(target_buffer))
                                    for name, target_buffer in targets
                                }

                            for (
                                _,
                                _,
                                _,
                                response,
                            ) in matches:
                                # Always send from the caller
                                # thread, never the listener.
                                self.send(
                                    response + "\n"
                                )

                            if not dialog_entries:
                                if not wait_for_prompt:
                                    return result

                                # Interactive dialog responses (most notably
                                # passwords) are not complete until the child
                                # program presents its configured prompt.  A
                                # fixed delay merely hides this race on fast
                                # machines and loses on slower ones.
                                dialog_prompt_matcher = re.compile(
                                    re.escape(self.prompt),
                                    re.I,
                                )

                        continue

                    callback_item = (
                        item[search_pos:search_end]
                        if is_initial
                        else item
                    )

                    callback_available = (
                        search_end >= search_pos
                        and (
                            not is_initial
                            or bool(callback_item)
                        )
                    )

                    for (
                        kind,
                        original,
                        matcher,
                    ) in matchers:
                        if kind == "regex":
                            match = matcher.search(
                                searchable,
                                search_pos,
                                search_end,
                            )

                            if match is None:
                                continue

                            match_end = match.end()
                            result = match

                        else:
                            if (
                                not callback_available
                                or not matcher(
                                    callback_item
                                )
                            ):
                                continue

                            match_end = search_end
                            result = original

                        commit_cursor(
                            buffer,
                            searchable,
                            match_end,
                        )
                        return result

                if failure is not None:
                    raise failure
                elif terminal == "closed":
                    raise EOFError(
                        "channel closed before the "
                        "pattern was matched"
                    )
                elif terminal == "timeout":
                    if silent:
                        return None

                    raise TimeoutError(
                        f"Not found: "
                        f"{timeout_target!r}"
                    )
        finally:
            try:
                for (
                    buffer,
                    listener,
                ) in reversed(registrations):
                    with buffer._condition:
                        for index in range(
                            len(buffer._listeners) - 1,
                            -1,
                            -1,
                        ):
                            if (
                                buffer._listeners[index]
                                is listener
                            ):
                                del buffer._listeners[index]
                                break
            finally:
                self._expect_owner = None
                self._expect_lock.release()

    def expect_old(self,rawpat,timeout=None,stdout=True,stderr=True,silent=False):
        """Block until a pattern is matched in output or timeout reached.
        
        This is a blocking function that waits for a pattern to appear in
        stdout or stderr. the searching target can not across lines.
        
        :rawpat:
            - a str,re.Pattern or a list,tuple of them
                if a list was given, one of list member matched, this expect() has completed.
            - callable , eg:
                def callback(item:str)->bool:
                    ## items is a list of str, which are just been appeneded into stdout or stderr
                    ## when True is returned, means the expect() has matched.
                    return True
            - dict, with str-keys
                eg. {'a':'b','c':'d'}
                if incoming stream (of stdout or stderr) matched 'a', then send 'b\n' to channel and 'a' is removed,
                if incoming stream (of stdout or stderr) matched 'c', then send 'd\n' to channel and 'c' is removed,
                when all keys were matched, this expect() has completed.
        :timeout:
            0 or None: waiting forever
        :stdout: Whether to search in stdout
        :stderr: Whether to search in stderr
        :silent:
            if False, raise TimeoutError when timeout 
            if True, raise nothing, None was returnedwhen timeout
        :return:
            None if timeout and silent=True
            when matched:
                - the matching object, when the rawpat is a str,re.Pattern or list,tuple of them
                - the callback which returns True, when the rawpat is a callback or list,tuple of callable
                - a dict of the same key with its matching object, when the rawpat is a dict
            
        :raise:
            TimeoutError: if timeout reached and silent=False
        """
        ## prepare matching objects
        ret = None
        regularPats = []
        callablePats = []
        text2send = []
        completed = False
        _stdout_with_listener = self._stdout if stdout else None
        _stderr_with_listener = self._stderr if stderr else None
        
        if isinstance(rawpat,dict):
            ##rawpat = dict(zip([x.lower() for x in rawpat.keys()],rawpat.values()))
            pats = list(rawpat.keys())
        elif (isinstance(rawpat,list) or isinstance(rawpat,tuple)):
            pats = rawpat
        else:
            pats = [rawpat]
        for pat in pats:
            if isinstance(pat,str):
                regularPats.append((re.compile(pat,re.I),pat))
            elif callable(pat):
                callablePats.append(pat)
            elif isinstance(pat,re.Pattern):
                assert isinstance(pat.pattern,str),f'expect() should be called with str-pattern, not "{pat.pattern}"'
                regularPats.append((pat,pat))
            else:
                raise ValueError('expect() only accept bytes,str,re.Pattern(str) or list of them')

        ## comparing starts below
        def remove_listener():
            nonlocal _stdout_with_listener
            nonlocal _stderr_with_listener
            if _stdout_with_listener:
                _stdout_with_listener.pop_listener(listener)
            if _stderr_with_listener:
                _stderr_with_listener.pop_listener(listener)

        def listener(item):
            """ 
            this routine would be called by stdio when new data was received
            return True if completed
            """
            nonlocal ret
            nonlocal completed
            nonlocal regularPats
            for callback in callablePats:
                if completed: break ## maybe stderr has matched by another thread 
                if callback(item):
                    completed = True
                    ret = callback
                    return
            idx = 0
            for pat,ret_key in regularPats[:]:
                if completed: break ## maybe stderr has matched by another thread 
                m = pat.search(item)
                if m:
                    if isinstance(rawpat,dict):
                        try:
                            ret[ret_key] = m
                        except TypeError:
                            ret = {ret_key: m}
                        ## not send text here, since this routine might be called
                        ##      in diffrent thread not same as expect() caller, 
                        ##      and sending here might cause deadlock 
                        #text2send.append(rawpat[m.group(0).lower()])
                        text2send.append(rawpat[pat.pattern])
                        regularPats.pop(idx)
                        if len(regularPats) == 0:
                            completed = True
                            break
                    else:
                        completed = True
                        ret = m
                        break
                idx += 1
        def set_listener()->bool:
            nonlocal _stdout_with_listener
            nonlocal _stderr_with_listener
            if stdout:
                _stdout_with_listener.push_listener(listener)
            if stderr:
                _stderr_with_listener.push_listener(listener)
        
        
        ## waiting for pattern shows up
        endTime = (time.time() + timeout) if timeout else 0       
        set_listener()
        try:
            while not completed:
                while len(text2send):
                    self.send(text2send.pop(0)+'\n')
                    self.wait_for_silent(1)

                ## checking timeout 
                if endTime == 0:
                    pass
                elif time.time() >= endTime:
                    if silent:
                        ret = None
                        break
                    else:
                        raise TimeoutError(f'Not found: {rawpat.keys() if isinstance(rawpat,dict) else rawpat}')
                time.sleep(0.1)
        except TimeoutError:
            raise
        else:
            ## sending residuals in text2send list
            while len(text2send):
                self.send(text2send.pop(0)+'\n')
                self.wait_for_silent(1)
        finally:
            remove_listener()

        return ret

    def __enter__(self):
        #self._enter_counter += 1
        pass
    
    def __exit__(self,exc_type, exc_value, traceback):
        ## when exception was raised, this channel could be closed already
        ## so, do nothing when it happens
        #self._enter_counter -= 1
        #assert self._enter_counter >= 0
        #if self._enter_counter == 0:
        #    self.close()
        return False
    
    #def send(self,raw_text):
    #    if self._sending_error is not None:
    #        raise self._sending_error
    #    while self.sending_queue.qsize(): time.sleep(0.01)
    #    self.sending_queue.put_nowait(raw_text)
    #    future = asyncio.run_coroutine_threadsafe(self.sending_queue.join(), self.interaction_loop)
    #    future.result()
    #    if self._sending_error is not None:
    #        raise self._sending_error


    ## condex suggested "send" and its helper
    def _remaining(self, deadline):
        if deadline is None:
            return None
        return max(0.0, deadline - time.monotonic())
    def _acquire_until(self, lock, deadline, description):
        while True:
            self._raise_if_unusable()

            remaining = self._remaining(deadline)
            if remaining is not None and remaining <= 0:
                raise TimeoutError(
                    f'timed out waiting for {description}'
                )

            interval = (
                0.05 if remaining is None
                else min(0.05, remaining)
            )

            if lock.acquire(timeout=interval):
                return
    async def _async_send(self, raw_text):
        async with self._async_send_lock:
            self._raise_if_unusable()

            loop = asyncio.get_running_loop()

            try:
                # raw_send()/sendall()/os.write() 都可能 blocking，
                # 不應直接阻塞 interaction event loop。
                await loop.run_in_executor(
                    None,
                    self.raw_send,
                    raw_text,
                )
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                self.fail(exc)
                raise

            self._raise_if_unusable()
    def send(self, raw_text, timeout=None):
        if timeout is None:
            timeout = self.send_timeout

        deadline = time.monotonic() + timeout

        if not self._interaction_ready.wait(
            timeout=self._remaining(deadline)
        ):
            raise TimeoutError(
                'timed out waiting for channel interaction startup'
            )

        self._raise_if_unusable()
        self._acquire_until(
            self._send_call_lock,
            deadline,
            'channel send lock',
        )

        future = None

        try:
            self._raise_if_unusable()
            future = asyncio.run_coroutine_threadsafe(
                self._async_send(raw_text),
                self.interaction_loop,
            )

            try:
                return future.result(
                    timeout=self._remaining(deadline)
                )
            except concurrent.futures.TimeoutError:
                exc = TimeoutError(
                    f'channel send exceeded {timeout} seconds'
                )
                future.cancel()
                self.fail(exc)
                raise exc
        finally:
            self._send_call_lock.release()    

    def raw_send(self,text):
        raise   NotImplementedError('raw_send() not implemented')


    async def async_start_interaction(self):
        self.interaction_loop = asyncio.get_running_loop()
        self._async_send_lock = asyncio.Lock()
        self._dumpCondition = asyncio.Condition()
        self._set_open()

        reader_task = asyncio.create_task(
            self._start_reading(),
            name='channel-reader',
        )
        dump_task = asyncio.create_task(
            self._dump_stdout_err_job(),
            name='channel-output-dumper',
        )

        tasks = {reader_task, dump_task}

        try:
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # 取得 exception；若 task 失敗，這裡會重新 raise。
            for task in done:
                task.result()

            with self._lock:
                state = self._state

            # Reader 在正常 close 之前結束，就是 EOF/channel failure。
            if state == 'open':
                raise EOFError(
                    'channel interaction ended unexpectedly'
                )

        except asyncio.CancelledError:
            with self._lock:
                closing = self._state in ('closing', 'closed')

            if not closing:
                self.fail(
                    EOFError('channel interaction was cancelled')
                )
            raise

        except BaseException as exc:
            self.fail(exc)
            raise

        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            self._interaction_stopped.set()

    '''
    async def async_start_interaction(self):
        self.interaction_loop = asyncio.get_event_loop()
        await asyncio.gather(self._start_reading(),self.consume_sending_queue(),self._dump_stdout_err_job())


    def start_interaction(self):
        def r():
            newloop = asyncio.new_event_loop()
            self.interaction_loop = newloop
            asyncio.set_event_loop(newloop)
            ## create another new Condition for this event loop
            self._dumpCondition = asyncio.Condition()
            if hasattr(asyncio, "get_child_watcher"):
                watcher = asyncio.get_child_watcher()
                watcher.attach_loop(newloop)
            task = newloop.create_task(self.async_start_interaction())
            try:
                newloop.run_forever()
            except Exception as e:
                traceback.print_exc()
            finally:
                task.cancel()
                newloop.run_until_complete(newloop.shutdown_default_executor())
                newloop.run_until_complete(newloop.shutdown_asyncgens())
                if hasattr(asyncio, "get_child_watcher"):                
                    try:
                        watcher.attach_loop(None)
                    except: pass 
                newloop.close()
                asyncio.set_event_loop(None)
        self.interaction_thread = threading.Thread(target=r,daemon=True,name='expect.call')
        self.interaction_thread.start()
    
    #async def consume_sending_queue(self):
    #    empty = asyncio.queues.QueueEmpty
    #    while not self.closed:
    #        try:
    #            text = self.sending_queue.get_nowait()
    #        except empty:
    #            await asyncio.sleep(0.1)
    #        else:
    #            try:
    #                self.raw_send(text)
    #            except Exception as e:
    #                self._sending_error = e
    #                self.sending_queue.task_done()
    #                raise
    #            else:
    #                self.sending_queue.task_done()
    #                ## let other coroutine has chances to work
    #                ## this is important
    #                await asyncio.sleep(0.1)
    
    
    def input(self,text):
        """Send text as input to the channel.
        
        :text: Text to send as input
        """
        logger.debug(
            '%s Sending channel input (length=%d, interactive=%s)',
            self.prefixOfLog,
            len(text),
            self.hijacked,
        )
        if self.hijacked:
            ## when hijacked, calling input() is likely to execute a command, 
            ## so we need to acquire the executing_lock to prevent other commands from running concurrently.
            ## caution: if user's last command is "exit", this lock would not be release
            ##      but it does not matter, becuase that layer would be removed as well as this lock
            self.executing_lock.acquire()
            self.reset_buffer()
            if self.prompt:
                def prompt_found_callback():
                    self._stdout.set_callback(None,None)
                    self._stderr.set_callback(None,None)
                    self.executing_lock.release()
                self._stdout.set_callback(prompt_found_callback,self.prompt)
                self._stderr.set_callback(prompt_found_callback,self.prompt)
        
        self.send(text+'\n')
        
        if self.hijacked:
            if self.prompt:
                ## the self.executing_lock.release() would be called in the prompt_found_callback() 
                ## when the prompt is found
                pass
            else:
                ## such as when entering a password
                ## release the lock after 1 second of silence (no output)
                self.wait_for_silent(1)
                self.executing_lock.release()
    '''
    def _wait_input_completion(
        self,
        current_prompt_found,
        stdout,
        stderr,
        parent_prompt,
        deadline,
    ):
        while True:
            remaining = self._remaining(deadline)
            if remaining <= 0:
                raise TimeoutError(
                    'timed out waiting for the current prompt '
                    'or interactive console exit'
                )

            if current_prompt_found.wait(min(0.05, remaining)):
                return 'prompt'

            # The layer has not been popped yet, so the parent prompt is
            # still delivered to the captured child-layer buffers.
            if parent_prompt and (
                parent_prompt in str(stdout)
                or parent_prompt in str(stderr)
            ):
                return 'exited'

            with self._lock:
                failure = self._failure
                state = self._state

            if failure is not None:
                raise failure

            if state in ('closing', 'closed'):
                raise EOFError(
                    'channel closed while waiting for the current prompt '
                    'or interactive console exit'
                )

            if state != 'open':
                raise BrokenPipeError(
                    'channel became unusable while waiting for input '
                    f'completion (state={state})'
                )

    def input(self, text, timeout=60):
        if not isinstance(text, str):
            raise TypeError('input text must be str')

        if (
            not isinstance(timeout, (int, float))
            or not 0 < float(timeout) < float('inf')
        ):
            raise ValueError(
                'input timeout must be a positive finite number'
            )

        if not self.hijacked:
            return self.send(text + '\n', timeout=timeout)

        deadline = time.monotonic() + timeout
        executing_lock = self.executing_lock
        self._acquire_until(
            executing_lock,
            deadline,
            'input execution lock',
        )

        stdout = None
        stderr = None
        current_prompt_found = threading.Event()

        try:
            # Check again after acquiring the lock. A prior waiter might
            # have exited the interactive child immediately before us.
            if self._interactive_layer_exited(executing_lock):
                raise EOFError(
                    'interactive console has already exited; '
                    'leave the with block before sending another input'
                )

            stdout,stderr = self.reset_buffer('input')[0]

            with self._lock:
                current_prompt = (
                    self.prompts[-1]
                    if self.prompts
                    else None
                )
                parent_prompt = (
                    self.prompts[-2]
                    if len(self.prompts) > 1
                    else None
                )

            # Equal prompts cannot identify which layer produced the match.
            if parent_prompt == current_prompt:
                parent_prompt = None

            if current_prompt:
                def prompt_found():
                    current_prompt_found.set()

                # Keep the existing behavior in which the current prompt is
                # removed from the captured output by DequeString.append().
                stdout.set_callback(prompt_found, current_prompt)
                stderr.set_callback(prompt_found, current_prompt)

            self.send(
                text + '\n',
                timeout=self._remaining(deadline),
            )

            if current_prompt:
                outcome = self._wait_input_completion(
                    current_prompt_found,
                    stdout,
                    stderr,
                    parent_prompt,
                    deadline,
                )
            else:
                remaining = self._remaining(deadline)
                self.wait_for_silent(
                    1,
                    max_seconds=max(0.01, remaining),
                )

                if parent_prompt and (
                    parent_prompt in str(stdout)
                    or parent_prompt in str(stderr)
                ):
                    outcome = 'exited'
                else:
                    outcome = 'silent'

            if outcome == 'exited':
                self._mark_interactive_layer_exited(
                    executing_lock
                )

            return outcome

        finally:
            if stdout is not None:
                stdout.set_callback(None, None)
            if stderr is not None:
                stderr.set_callback(None, None)

            executing_lock.release()    

    def get_exit_code(self,timeout=60):
        """Get the exit code of the last command.
        
        :timeout: Maximum time to wait for exit code
        """
        
        assert not self.closed
        assert not self.hijacked
        deadline = None if timeout in (None, 0) else time.monotonic() + timeout
        executing_lock = self.executing_lock
        ## important for stability
        self._acquire_until(
            executing_lock,
            deadline,
            'get exit code',
        )
        stdout,stderr = None,None    
        origin_layer = None
        try:
            new_layer, origin_layer = self.reset_buffer('get_exit_code')
            stdout,stderr = new_layer

            sno = self._increase_exitcode_sno()
            pat = self.exitcodePatterns[sno]
            ## save stdio buffer
            completed = threading.Event()
            def prompt_found_callback():
                completed.set()

            if self.prompt:
                stdout.set_callback(prompt_found_callback,self.prompt)
                stderr.set_callback(prompt_found_callback,self.prompt)
                self.send(f'echo "_{sno}_$?_{sno}{sno}_"\n', timeout=self._remaining(deadline))
            else:
                ## take "-@@-" as the prompt to know the exitcode has been outputed
                stdout.set_callback(prompt_found_callback,'-@@-')
                stderr.set_callback(prompt_found_callback,'-@@-')
                self.send(f'echo "_{sno}_$?_{sno}{sno}_-@@-"\n', timeout=self._remaining(deadline))

            self._wait_event(
                completed,
                deadline,
                'exit code retrieval'
            )

            m = pat.search(str(stdout))
            if m:
                self._exitcode = int(m.group(2))
            else:
                m = pat.search(str(stderr))
                if m:
                    self._exitcode = int(m.group(2))
                else:
                    raise RuntimeError(
                        'exit code retrieval completed without a valid exit status'
                    )
        finally:
            try:
                with self._lock:
                    if stdout is not None:
                        stdout.set_callback(None,None)
                    if stderr is not None:
                        stderr.set_callback(None,None)
                    if origin_layer is not None:
                        ## if state changed, close the original stdout, stderr
                        origin_layer_restored = False
                        if not self._state in ('closing','closed'):
                            ## restore origin_layer to stdio_store
                            for index, current_layer in enumerate(self.stdio_store):
                                if current_layer is new_layer:
                                    self.stdio_store[index] = origin_layer
                                    origin_layer_restored = True
                                    break
                        ## if not restored, close them to ensure file handles are not leaked
                        if not origin_layer_restored:
                            for stream in origin_layer:
                                if not stream.closed:
                                    stream.close()
                        # common cleanup：不應放在任何 state 分支內
                        for stream in new_layer:
                            if not stream.closed:
                                stream.close()

            finally:
                executing_lock.release()

        return self._exitcode
    

    ## send_command's helper
    def _wait_event(self, event, deadline, description):
        while True:
            if event.wait(timeout=0.05):
                return

            self._raise_if_unusable()

            remaining = self._remaining(deadline)
            if remaining is not None and remaining <= 0:
                raise TimeoutError(
                    f'timed out waiting for {description}'
                )
    ## run the commands    
    def send_line(self,line,**expections):
        """Send a line or multiple lines to the channel.
        
        :line: String or list of strings to send
        """
        assert not self.hijacked, 'can not sendline when hijacked'

        return self.send_command(line,**expections)

    def send_command(
        self,
        command,
        *,
        command_timeout=60,
        **expections,
    ):
        deadline = time.monotonic() + command_timeout
        executing_lock = self.executing_lock
        self._acquire_until(
            executing_lock,
            deadline,
            'command execution lock',
        )

        stdout = None
        stderr = None
        completed = threading.Event()

        try:
            self._exitcode = EXITCODE_DEFAULT
            # 保存確切 buffer；finally 不應清到下一個 layer 的 callback。
            stdout,stderr = self.reset_buffer()[0]

            def command_completed():
                completed.set()

            if self.prompt:
                stdout.set_callback(
                    command_completed,
                    self.prompt,
                )
                stderr.set_callback(
                    command_completed,
                    self.prompt,
                )

                self.send(
                    command + '\n',
                    timeout=self._remaining(deadline),
                )

            else:
                stdout.set_callback(
                    command_completed,
                    '-@_@-',
                )

                self.send(
                    f'{{ {command}; }} ; '
                    'echo _TT$?_-@_@-\n',
                    timeout=self._remaining(deadline),
                )

            # expectation input 不要呼叫可能重新 acquire lock 的 input()。
            #pending = {
            #    key.lower(): value
            #    for key, value in expections.items()
            #}
            pending = dict(expections)

            while pending:
                remain = self._remaining(deadline)
                if remain <= 0:
                    raise TimeoutError(
                        'timed out waiting for command expectations'
                    )
                match = self.expect(
                    list(pending),
                    timeout=remain,
                )
                ## recalculate remain, since expect() might take a long time to return
                remain = self._remaining(deadline)
                if remain <= 0:
                    raise TimeoutError(
                        'timed out waiting for command expectations'
                    )
                self.send(
                    pending.pop(match.re.pattern) + '\n',
                    timeout=remain
                )

            self._wait_event(
                completed,
                deadline,
                'command completion',
            )

            if not self.prompt:
                match = re.compile(
                    r'_TT(\d+)_'
                ).search(str(stdout))

                if match is None:
                    raise RuntimeError(
                        'command completed without a valid exit status'
                    )

                self._exitcode = int(match.group(1))

            return stdout, stderr

        finally:
            if stdout is not None:
                stdout.set_callback(None, None)
            if stderr is not None:
                stderr.set_callback(None, None)

            # callback 不再 release，所以這裡可確定只釋放一次。
            executing_lock.release()    


    r'''
    def send_command(self,command,**expections):
        """Send a command to the channel.       
        :command: Command to execute
        :expections: expected prompts and corresponding input, e.g.

        :return: Tuple of (stdout, stderr)
        """
        logger.debug(
            '%s Dispatching command (interactive=%s, expectations=%d) %s',
            self.prefixOfLog,
            bool(self.prompt),
            len(expections),
            [f'"{command_summary(command)}"']
        )
        
        ## ensure that there is no more output, especially at the beginning when a new shell is started
        self.executing_lock.acquire()
        self._exitcode = EXITCODE_DEFAULT
        self.reset_buffer()
        ## for powershell, send \n would get \n back; send \r\n would get \r\n back
        #if self.prompt:
        #    result = self.send(command+'\n')
        #else:
        #    ## embedding the echo command to make sure we know it is completed and getting the exitcode
        #    ## don't use "\t" in echo, it is not stable
        #    result = self.send(f"{{ {command}; }} ; echo _TT$?_-@_@-\n")

        def handle_expections():
            lowerkey_expections = dict(zip([x.lower() for x in expections.keys()],expections.values()))
            while len(lowerkey_expections):
                m = self.expect(list(lowerkey_expections.keys()),timeout=60)
                self.input(lowerkey_expections[m.group(0).lower()])
                del lowerkey_expections[m.group(0).lower()]

        if self.prompt:
            def prompt_found_callback():
                self._stdout.set_callback(None,None)
                self._stderr.set_callback(None,None)
                self.executing_lock.release()
            self._stdout.set_callback(prompt_found_callback,self.prompt)
            self._stderr.set_callback(prompt_found_callback,self.prompt)
            
            result = self.send(command+'\n')
            if len(expections): handle_expections()
            
            ## why not wait for the lock to be released as below?
            while self.executing_lock.locked(): time.sleep(0.01)
        else:
            ## waiting for the echo command to output the exitcode,
            ## and take it as the signal of command completion
            def prompt_found_callback():
                m = re.compile(r'_TT(\d+)_').search(str(self._stdout))
                if m:
                    self._exitcode = int(m.group(1))
                else:
                    logger.warning(
                        '%s Unable to parse command exit status',
                        self.prefixOfLog,
                    )
                self._stdout.set_callback(None,None)
                self.executing_lock.release()
            self._stdout.set_callback(prompt_found_callback,'-@_@-')

            ## embedding the echo command to make sure we know it is completed and getting the exitcode
            ## don't use "\t" in echo, it is not stable
            result = self.send(f"{{ {command}; }} ; echo _TT$?_-@_@-\n")
            if len(expections): handle_expections()
            
            ## in this case, waiting for lock to be released is waiting for the exitcode to be retrieved,
            ## so that when next line is getting $.exitcode, it would get the corrent exitcode
            ## not the exitcode of our modified command.
            while self.executing_lock.locked(): time.sleep(0.01)
        logger.debug(
            '%s Command completed (interactive=%s, exit_status=%s)',
            self.prefixOfLog,
            bool(self.prompt),
            None if self.prompt else self._exitcode,
        )
        return self._stdout, self._stderr
    '''

    def send_signal(self,sig):
        """Send a signal to the process.
        
        :sig: Signal to send
        """
        if getattr(self, 'is_ssh_channel', False):
            message = paramiko.Message()
            message.add_byte(paramiko.common.cMSG_CHANNEL_REQUEST)
            message.add_int(self.channel.channel.remote_chanid)
            message.add_string("signal")
            message.add_boolean(False)
            message.add_string(sig.name[3:])
            #message.add_string('TERM')
            self.channel.channel.transport._send_user_message(message) 
        else:
            self.cp.send_signal(sig)

    async def _add_stdout_data(self,newbytes): 
        """Add data to stdout buffer.
        
        :newbytes: Bytes to add to stdout
        """
        with self._lock:
            ## by checking self.closed, "exit" would not be put into stdout
            if self.closed: return
            self.touchIO(True)
            try:
                self._stdout.append(newbytes.decode('utf8'),True)
            except UnicodeDecodeError:
                self._stdout.append(newbytes.decode('utf8','replace'),True)
        if self.dump2sys[0]:
            if self._dumpCondition is None:
                self._dumpCondition = asyncio.Condition()
            async with self._dumpCondition:
                self._dumpBuf.append((0,newbytes))
                self._dumpCondition.notify()

    async def _add_stderr_data(self,newbytes):
        """Add data to stderr buffer.
        
        :newbytes: Bytes to add to stderr
        """
        with self._lock:         
            ## by checking self.closed, "exit" would not be put into stdout
            if self.closed: return
            self.touchIO(True)
            try:
                self._stderr.append(newbytes.decode('utf8'),True)
            except UnicodeDecodeError:
                self._stderr.append(newbytes.decode('utf8','replace'),True)
        if self.dump2sys[1]:
            if self._dumpCondition is None:
                self._dumpCondition = asyncio.Condition()
            async with self._dumpCondition:
                self._dumpBuf.append((1,newbytes))
                self._dumpCondition.notify()

    ## v2.0.3, adds an delegated thread to dump stdout,stderr to console
    async def _dump_stderr(self,newbytes):
        try:
            p = newbytes.rindex(b'\n')
        except ValueError:
            self._stderrDumpBuf += newbytes
        else:
            content = self._stderrDumpBuf + newbytes[:p]
            for line in content.splitlines():
                sys.stderr.buffer.write(self.stderrPrefix+self._native_id.encode()+b':'+line+b'\n')
            self._stderrDumpBuf = newbytes[p+1:]
            sys.stderr.buffer.flush()        

    async def _dump_stdout(self,newbytes):
        ''' print to console line by line, no print if no new line'''
        try:
            p = newbytes.rindex(b'\n')
        except ValueError:
            self._stdoutDumpBuf += newbytes
        else:
            content = self._stdoutDumpBuf + newbytes[:p]
            for line in content.splitlines():
                sys.stdout.buffer.write(self.stdoutPrefix+self._native_id.encode()+b':'+line+b'\n')
            self._stdoutDumpBuf = newbytes[p+1:]
            sys.stdout.buffer.flush()

    async def _dump_stdout_err_job(self):
        """Background thread function to dump stdout/stderr to console.
        
        This method runs in a separate thread and handles writing
        stdout/stderr data to the console with appropriate prefixes.
        """
        handler = [self._dump_stdout,self._dump_stderr]
        #while not (self.closed or self._dumpBuf.closed):
        while not self.closed:
            try:
                async with self._dumpCondition:
                    if self.closed: break
                    try:
                        await self._dumpCondition.wait()
                    except (asyncio.exceptions.CancelledError,GeneratorExit):
                        break
                    except asyncio.exceptions.TimeoutError:
                        if self.closed:# or self._dumpBuf.closed:
                            break
                        else:
                            try:
                                ## important for avoiding blocking the event loop
                                await asyncio.sleep(0.01)
                            except asyncio.exceptions.CancelledError:
                                break                            
                    else:
                        for x,newbytes in self._dumpBuf:
                            await handler[x](newbytes)
                        self._dumpBuf.clear()
            except Exception:
                logger.exception('%s Channel output forwarding failed', self.prefixOfLog)
                raise
    async def _dump_stdout_err(self):
        handler = [self._dump_stdout,self._dump_stderr]
        for x,newbytes in self._dumpBuf:
            await handler[x](newbytes)
        self._dumpBuf.clear()
    
    def reset_buffer(self,reason=None):
        """
        Replace a pair of stdout,stderr to stdio_store,
        aka. clear the self.stdout and self.stderr
        """
        ## clean up console.stdout, console.stderr
        with self._lock: 
            self._raise_if_unusable()
            origin_layer = self.stdio_store[-1]
            new_layer = (SSHScriptStdout(),SSHScriptStderr())
            self.stdio_store[-1] = new_layer
            self.touchIO(0)
            self.touchIO(1)
            return new_layer, origin_layer
    clear = reset_buffer

    def close(self):        
        """Close the channel and cleanup resources.
        
        Ensures exit code is retrieved before closing.
        """
        if not self._begin_close():
            return
        self._finish_close()
