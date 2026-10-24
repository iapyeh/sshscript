"""Persistent text console for humans and agents using a retained terminal session."""
import argparse
import ast
import builtins
import code
from io import StringIO
import tokenize
import traceback
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
import threading
from getpass import getpass, GetPassWarning
import re
import warnings
import sys
import time
import subprocess

if __package__:
    from . import dollarparser, tokenparser, patching
    from .session import Session
    from .commandresult import CommandResult
    from .commandjob import JobResult
else:
    import dollarparser, tokenparser, patching
    from session import Session
    from commandresult import CommandResult
    from commandjob import JobResult


class _LeaveLayer(BaseException):
    def __init__(self, command=None):
        self.command = command


class _QuitConsole(BaseException):
    pass


class _ConsoleSyntax(ast.NodeTransformer):
    """Route prompt-level dollar syntax through the environment manager.

    Lexical with blocks retain the normal .spy compiler's context ownership.
    Generated names are changed as AST nodes, never by replacing source strings.
    """
    def __init__(self):
        self.lexical_depth = 0

    def visit_With(self, node):
        self.lexical_depth += 1
        try:
            return self.generic_visit(node)
        finally:
            self.lexical_depth -= 1

    visit_AsyncWith = visit_With

    def visit_Name(self, node):
        if not self.lexical_depth and node.id in ('_sshscript_in_context_', '_c'):
            return ast.copy_location(ast.Name(id='_console_control_', ctx=node.ctx), node)
        return node

    def visit_Call(self, node):
        if (not self.lexical_depth and isinstance(node.func, ast.Name)
                and node.func.id in ('exec_command', 'onedollar', 'twodollars')):
            node.func = ast.copy_location(ast.Attribute(
                value=ast.Name(id='_console_control_', ctx=ast.Load()),
                attr='exec_command', ctx=ast.Load()), node.func)
        return self.generic_visit(node)

    def visit_Expr(self, node):
        raw_command = (isinstance(node.value, ast.Call)
                       and isinstance(node.value.func, ast.Name)
                       and node.value.func.id in ('exec_command', 'onedollar', 'twodollars'))
        node = self.generic_visit(node)
        if raw_command:
            # A raw shell line displays its output, not a JobResult repr.
            return ast.copy_location(ast.Assign(
                targets=[ast.Name(id='result', ctx=ast.Store())], value=node.value), node)
        return node


class _PythonConsole(code.InteractiveConsole):
    def __init__(self, namespace):
        super().__init__(namespace)
        self.cell = 1
        self.last_error = None

    def runsource(self, source, filename='<input>', symbol='single'):
        filename = f'<sshscript-console-{self.cell}>'
        try:
            try:
                compiled = self.compile(source, filename, symbol)
            except SyntaxError:
                # Use the existing tokenizer/compiler for dollar syntax, including
                # properties inside Python expressions and f-strings.
                try:
                    translated = tokenparser.convert(source)
                except tokenize.TokenError as error:
                    if error.args[0] in ('EOF in multi-line statement',
                                         'EOF in multi-line string',
                                         'unexpected EOF in multi-line statement',
                                         'unexpected EOF in multi-line string'):
                        # Older tokenizers also report EOF after an unmatched
                        # closing delimiter. That is invalid, not unfinished.
                        delimiters = []
                        pairs = {')': '(', ']': '[', '}': '{'}
                        try:
                            for token in tokenize.generate_tokens(StringIO(source).readline):
                                if token.type != tokenize.OP:
                                    continue
                                if token.string in ('(', '[', '{'):
                                    delimiters.append(token.string)
                                elif token.string in pairs:
                                    if not delimiters or delimiters.pop() != pairs[token.string]:
                                        diagnostic = SyntaxError(
                                            f'unmatched {token.string!r}',
                                            (filename, token.start[0], token.start[1] + 1, None))
                                        raise dollarparser._source_syntax_error(
                                            diagnostic, filename, source) from None
                        except tokenize.TokenError:
                            pass
                        return True
                    raise dollarparser._token_syntax_error(error, filename, source) from None
                try:
                    compiled = self.compile(translated, filename, symbol)
                except SyntaxError as error:
                    raise dollarparser._source_syntax_error(error, filename, source) from None
                if compiled is not None:
                    tree = dollarparser.parse(filename, source, preprocess=_ConsoleSyntax())
                    # The script compiler adds stack setup; keep future imports
                    # before that setup when compiling an interactive cell.
                    futures = [n for n in tree.body if isinstance(n, ast.ImportFrom)
                               and n.module == '__future__']
                    body = futures + [n for n in tree.body if n not in futures]
                    tree = ast.Interactive(body=body) if symbol == 'single' else ast.Module(body=body, type_ignores=[])
                    compiled = compile(ast.fix_missing_locations(tree), filename, symbol,
                                       flags=self.compile.compiler.flags)
            if compiled is None:
                return True
        except (SyntaxError, OverflowError, ValueError) as error:
            self.locals["error"] = error
            self.cell += 1
            self.last_error = type(sys.exc_info()[1]).__name__
            self.showsyntaxerror(filename)
            return False
        self.cell += 1
        self.runcode(compiled)
        return False

    def showsyntaxerror(self, filename=None):
        self.write("SyntaxError: input compilation failed; use :error or :traceback for details.\n")

    def runcode(self, code_object):
        try:
            exec(code_object, self.locals)
        except (_LeaveLayer, _QuitConsole, SystemExit, KeyboardInterrupt):
            raise
        except BaseException as error:
            self.last_error = type(error).__name__
            self.locals['error'] = error
            # Source and exception text may contain credentials.
            self.write(f'{type(error).__name__}: operation failed; use :error or :traceback for details.\n')



@dataclass
class _Layer:
    resources: ExitStack
    session: Session
    console: object
    kind: str
    host: str
    user: str
    result: object = None
    program_buffers: tuple = ()
    program_positions: tuple = (0, 0)
    exit_command: str | None = None
    input_tail: str = ''
    secret_pending: bool = False


_SECRET_PROMPT = re.compile(
    r'(?:\[sudo\]\s*)?(?:(?:enter|confirm|retype|new|current|old)\s+)*'
    r"(?:[\w.@+-]+'s\s+)?(?:UNIX\s+)?"
    r'(?:password|passphrase|pin|token|verification code|one[- ]time (?:password|code))'
    r'(?:\s+for\b[^\r\n:：]*)?\s*[:：]\s*|'
    r'(?:請)?(?:輸入|输入)(?:密碼|密码|驗證碼|验证码|PIN|token)\s*[:：]\s*',
    re.IGNORECASE)
_TERMINAL_ESCAPE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')



class CredentialsRequiredError(ValueError):
    """A managed identity switch needs an explicit credential decision."""


class ConsoleInitializationError(RuntimeError):
    """Initialization failed; the supplied Session needs reconciliation."""
    session_reuse = 'unknown'


class ConsoleCleanupError(RuntimeError):
    """Cleanup or the post-cleanup Session probe failed; reuse is unknown."""
    session_reuse = 'unknown'


@dataclass(frozen=True)
class Environment:
    kind: str
    host: str
    connection_user: str | None
    effective_user: str
    identity_verified: bool


@dataclass(frozen=True)
class SwitchRequest:
    kind: str
    username: str | None
    environment: Environment
    credential_supplied: bool


@dataclass(frozen=True)
class SwitchCredentials:
    password: str | None = field(repr=False)


@dataclass(frozen=True)
class SwitchOutcome:
    request: SwitchRequest
    success: bool
    environment: Environment
    error_type: str | None = None


@dataclass(frozen=True)
class ConsoleUpdate:
    state: str
    stdout: str = ''
    stderr: str = ''
    result: CommandResult[int | None] | None = None
    error_type: str | None = None
    session_reuse: str = 'in_use'



class Console:
    """Persistent Python/dollar console shared by terminal and embedded callers.

    Borrow a supplied Session by default; explicitly transfer ownership with
    ownership="owned". Use a context manager or always call close().
    """

    def __init__(self, session, *, ownership='borrowed', terminal=False,
                 get_pty=True, credential_resolver=None, switch_observer=None,
                 stdout=None, stderr=None, input_func=None, password_func=None):
        if ownership not in ('borrowed', 'owned'):
            raise ValueError('ownership must be borrowed or owned')
        if session.closed:
            raise RuntimeError('Session is closed')
        self._creator = threading.get_ident()
        self._session = session
        self._ownership = ownership
        self._terminal = terminal
        self._resolver = credential_resolver
        self._observer = switch_observer
        self._capture = (StringIO(), StringIO())
        self._job = None
        self._job_positions = [0, 0]
        self._state = 'ready'
        self._error_type = None
        self._reuse = 'in_use'
        self._cleanup_error = None
        self._uncertain = False
        self._last_result = None
        self._submitting = False
        self._stdout = stdout if stdout is not None else (sys.stdout if terminal else self._capture[0])
        self._stderr = stderr if stderr is not None else (sys.stderr if terminal else self._capture[1])
        self.input_func = input_func or input
        self.password_func = password_func or (self._terminal_password if terminal else self._missing_password)
        self.layers = []
        self.namespace = {'__name__': '__console__', 'getpass': self.password_func,
                          'control': self, '_console_control_': self,
                          'patching': patching, 'result': None, 'error': None}
        self._helpers = {'help': self.help, 'exit': self._exit_layer, 'quit': self.quit}
        self.namespace.update(self._helpers)
        self.python = _PythonConsole(self.namespace)
        self.more = False
        self.done = False
        # Do not enter/exit the external Session or mutate its execution settings.
        try:
            with ExitStack() as resources:
                wrapper = session.shell('bash', get_pty=get_pty)
                wrapper.channel.dump2sys = (0, 0)
                shell = resources.enter_context(wrapper)
                self._push(resources, session, shell, 'ssh' if session.host else 'local',
                           session.host or 'local')
        except BaseException:
            self._reuse = 'unknown'
            if ownership == 'owned':
                try:
                    session.close(strict=True)
                except BaseException:
                    pass
            raise ConsoleInitializationError('console initialization failed; Session reuse is unknown') from None

    @property
    def current(self):
        if not self.layers:
            raise RuntimeError('console is not open')
        return self.layers[-1]

    def _refresh(self):
        self.namespace.update(session=self.current.session,
                              console=self.current.console,
                              _sshscript_session_=self.current.session)

    def _push(self, resources, session, console, kind, host, *, program=False):
        user = '?' if program else console('id -un', check=True).stdout.strip()
        self.layers.append(_Layer(resources.pop_all(), session, console, kind, host, user))
        self._refresh()

    def shell(self, *args, **kwargs):
        self._console_layer('shell', *args, **kwargs)

    def sudo(self, *args, **kwargs):
        self._identity_layer('sudo', *args, **kwargs)

    def su(self, *args, **kwargs):
        self._identity_layer('su', *args, **kwargs)

    def enter(self, *args, **kwargs):
        """Explicitly enter a text program; configure its prompt and exit text."""
        self._console_layer('enter', *args, **kwargs)

    def _exit_layer(self):
        self.exit()

    def exit(self, command=None):
        """Leave one console layer, optionally sending a program's exit command.

        Without an explicit or configured command, an entered program stays open.
        Prompt-level calls unwind the current Python cell before leaving.
        """
        self._check(idle=True)
        if command is not None:
            if not isinstance(command, str):
                raise TypeError('exit command must be str or None')
            if not command.strip() or '\n' in command or '\r' in command:
                raise ValueError('exit command must be a nonempty single line')
            if self.current.kind != 'program':
                raise ValueError('exit command requires an enter() program')
        if self._submitting:
            raise _LeaveLayer(command)
        self._request_exit(command)

    def _request_exit(self, command=None):
        if self.current.kind != 'program':
            self.leave()
            return
        command = command if command is not None else self.current.exit_command
        if command is None:
            self._write('Program remains open: use $.exit("exit command") or enter its native exit command.\n', self._stderr)
            self._state = 'running'
            return
        self._send_input(command)
        if self.layers and self.current.kind == 'program':
            self._write('Program has not returned to its parent shell; current layer remains open.\n', self._stderr)


    def quit(self):
        """Unwind Python contexts before closing every managed layer."""
        raise _QuitConsole()

    def help(self, *args, **kwargs):
        if not args and not kwargs:
            self._write(HELP + '\n', self._stdout)
            return None
        return builtins.help(*args, **kwargs)

    def _bare_helper(self, line):
        try:
            node = ast.parse(line, mode='eval').body
        except SyntaxError:
            return None
        if self.current.kind == 'program':
            if (isinstance(node, ast.Call) and not node.args and not node.keywords
                    and isinstance(node.func, ast.Name) and node.func.id in ('exit', 'quit')):
                node = node.func
            if not isinstance(node, ast.Name) or node.id not in ('exit', 'quit'):
                return None
        if (isinstance(node, ast.Name) and node.id in self._helpers
                and self.namespace.get(node.id) is self._helpers[node.id]):
            return node.id
        return None

    def stop(self, *args, **kwargs):
        return self.current.session.stop(*args, **kwargs)

    def run(self, source, vars=None, showScript=False):
        """Run a script in the current connection Session; stop returns here."""
        if vars is None:
            vars = dict(self.namespace)
            # Console convenience helpers must not change a child script's
            # ordinary Python exit()/quit()/help() semantics.
            for name, helper in self._helpers.items():
                if vars.get(name) is helper:
                    del vars[name]
        return self.current.session.run(source, vars, showScript)

    def run_file(self, path, **kwargs):
        if __package__:
            from .sshscript import run_file
        else:
            from sshscript import run_file
        return run_file(path, **kwargs)

    def __getattr__(self, name):
        # Non-environment operations keep the regular API's session/console owner.
        if name in ('upload', 'download', 'pkey', 'set', 'get'):
            return getattr(self.current.session, name)
        if name in ('send', 'expect'):
            return getattr(self.current.console, name)
        if name in ('stdout', 'stderr', 'exitcode'):
            if self.current.kind == 'program':
                return getattr(self.current.console, name)
            result = self.current.result
            return getattr(result, name) if result is not None else (None if name == 'exitcode' else '')
        raise AttributeError(name)

    def _write(self, text, stream):
        if text:
            stream.write(text)
            stream.flush()

    def exec_command(self, command, *, check=None, timeout=None,
                     capture_limit=8 * 1024 * 1024, stop_timeout=3):
        """Execute a dollar command in the current shell and retain its snapshot."""
        enabled = self.current.session.check if check is None else check
        if not isinstance(enabled, bool):
            raise TypeError('check must be bool')
        result = self._command(command, timeout=timeout, capture_limit=capture_limit,
                               stop_timeout=stop_timeout)
        if (enabled and result is not None and (not isinstance(result, JobResult) or result.stop_reason == 'completed')
                and result.exitcode != 0):
            error = subprocess.CalledProcessError(result.exitcode, command,
                                                 output=result.stdout, stderr=result.stderr)
            error.result = result
            raise error
        return result

    def _drain_program(self):
        layer = self.current
        channel = layer.console.channel
        buffers = (channel._stdout, channel._stderr)
        positions = []
        for index, (buffer, stream) in enumerate(zip(buffers, (self._stdout, self._stderr))):
            text = str(buffer)
            previous = (layer.program_positions[index]
                        if layer.program_buffers and layer.program_buffers[index] is buffer
                        else 0)
            visible = text[previous:]
            if (channel._interactive_layer_exited(channel.executing_lock)
                    and len(channel.prompts) > 1):
                parent_prompt = channel.prompts[-2]
                if isinstance(parent_prompt, str):
                    visible = visible.replace(parent_prompt, '')
            self._write(visible, stream)
            if visible:
                layer.input_tail = (layer.input_tail + visible)[-1024:]
                tail = _TERMINAL_ESCAPE.sub('', layer.input_tail)
                tail = re.split(r'[\r\n]', tail)[-1].strip()
                layer.secret_pending = _SECRET_PROMPT.fullmatch(tail) is not None
            positions.append(len(text))
        layer.program_buffers = buffers
        layer.program_positions = tuple(positions)

    def _program_control(self, character):
        """Send Ctrl-C/D without a newline and observe the program's real prompts."""
        self._drain_program()
        self.current.input_tail = ''
        self.current.secret_pending = False
        channel = self.current.console.channel
        try:
            outcome = channel._input_text(character, timeout=2, append_newline=False)
        except TimeoutError:
            # A program may ignore the control byte. Do not invent an exit.
            outcome = None
        self._drain_program()
        if outcome == 'exited':
            self.leave()
        else:
            # _input_text consumes a matched prompt from its output buffers.
            # Preserve the protocol result: poll cannot rediscover that prompt.
            self._state = 'waiting_input' if outcome == 'prompt' else 'running'

    def _eof(self):
        if self.layers and self.current.kind == 'program':
            self._program_control('\x04')
        else:
            self.python.resetbuffer()
            self.more = False
            self.close()

    @property
    def prompt(self):
        if self.more:
            return '... '
        layer = self.current
        suffix = ' program' if layer.kind == 'program' else ''
        return f'{layer.host} [{layer.user}]{suffix}> '

    def interact(self):
        if self.input_func is builtins.input and sys.stdin.isatty():
            # Python loads readline for its own REPL, but not when running a
            # script. Enable terminal editing before our first input() call.
            try:
                import readline  # noqa: F401
            except ImportError:
                pass  # Minimal Python builds retain input()'s basic editing.
        self._write('SSHScript console. Type help for commands; quit to finish.\n', self._stdout)
        try:
            while not self.done:
                try:
                    self._poll()
                    if self.done:
                        break
                    if self.current.kind == 'program' and self.current.secret_pending:
                        self.input(secret=True)
                        continue
                    line = self.input_func(self.prompt)
                except EOFError:
                    self.eof()
                    continue
                except KeyboardInterrupt:
                    self.interrupt()
                    continue
                try:
                    self.submit(line)
                    while self._job is not None:
                        update = self.poll()
                        if update.state == 'failed':
                            diagnostic = (f'exit {update.result.exitcode}' if update.result is not None
                                          and update.result.exitcode is not None
                                          else update.error_type or 'operation failed')
                            self._write(f'[{diagnostic}]\n', self._stderr)
                        if self._job is not None:
                            time.sleep(0.03)
                except KeyboardInterrupt:
                    self.interrupt()
                except Exception as error:
                    # Avoid echoing credential-bearing expressions or arbitrary
                    # server error text; the original exception is available as error.
                    self.namespace['error'] = error
                    self._write('Operation failed (' + type(error).__name__ + '). Use :error or :traceback for details.\n', self._stderr)
        finally:
            self.close()

    def _release_layer(self):
        layer = self.layers.pop()
        try:
            layer.resources.close()
        finally:
            if self.layers:
                self._refresh()
            else:
                self.done = True
                self.namespace.update(session=None, console=None)

    def _submit_line(self, line):
        """Process one input line; variables and contexts survive later calls."""
        if self.done:
            return
        try:
            helper = self._bare_helper(line) if not self.more else None
            if helper == 'quit':
                self.quit()
            elif helper == 'help':
                self.help()
            elif helper == 'exit':
                self._exit_layer()
            elif not self.more and line.strip() in (':error', ':traceback'):
                error = self.namespace.get('error')
                if error is None:
                    self._write('No recorded error.\n', self._stderr)
                else:
                    detail = (traceback.format_exception(error) if line.strip() == ':traceback'
                              else traceback.format_exception_only(type(error), error))
                    self._write(''.join(detail), self._stderr)
            elif not self.more and line.strip() == ':status':
                for layer in self.layers:
                    self._write(f'{layer.kind}: {layer.host} [{layer.user}]\n', self._stdout)
                self._write('Transfers and SSH credentials use the connection account.\n', self._stdout)
            else:
                with redirect_stdout(self._stdout), redirect_stderr(self._stderr):
                    self.more = self.python.push(line)
        except _QuitConsole:
            self.python.resetbuffer()
            self.more = False
            self.close()
        except KeyboardInterrupt:
            self._interrupt()
        except _LeaveLayer as request:
            self.python.resetbuffer()
            self.more = False
            self._request_exit(request.command)
        except SystemExit as error:
            self.python.last_error = type(error).__name__
            self.python.resetbuffer()
            self.more = False
            self._write('Python/script exited; console remains open.\n', self._stderr)
        finally:
            self._discard_failed_layers()

    @staticmethod
    def _terminal_password(prompt='Password: '):
        if not sys.stdin.isatty():
            raise CredentialsRequiredError('terminal password input requires a terminal or host-provided credentials')
        try:
            with warnings.catch_warnings():
                # Never let getpass fall back to echoed stdin input.
                warnings.simplefilter('error', GetPassWarning)
                return getpass(prompt)
        except GetPassWarning:
            raise CredentialsRequiredError('password input cannot disable terminal echo') from None

    @staticmethod
    def _missing_password(*args, **kwargs):
        raise CredentialsRequiredError('non-terminal console requires host-provided credentials')

    def _check(self, *, idle=False):
        if threading.get_ident() != self._creator:
            raise RuntimeError('Console operations require the constructing thread')
        if idle and self._job is not None:
            raise RuntimeError('poll or interrupt the foreground job before another operation')

    @property
    def connection(self):
        """The current connection Session; its login identity is unchanged by su/sudo."""
        self._check()
        return self.current.session

    @property
    def environments(self):
        self._check()
        return tuple(Environment(layer.kind, layer.host, layer.session.username,
                                 (self.layers[index - 1].user if layer.kind == 'program'
                                  and index else layer.user), layer.kind != 'program')
                     for index, layer in enumerate(self.layers))

    @property
    def session_reuse(self):
        return self._reuse

    def _identity_layer(self, kind, *args, **kwargs):
        self._check(idle=True)
        username = (args[0] if kind == 'su' and args else kwargs.get('username'))
        if kind == 'sudo' and len(args) > 1:
            username = args[1]
        supplied = 'password' in kwargs or len(args) >= (2 if kind == 'su' else 1)
        request = SwitchRequest(kind, username, self.environments[-1], supplied)
        try:
            credential = self._resolver(request) if self._resolver else None
            if credential is not None:
                if not isinstance(credential, SwitchCredentials):
                    raise TypeError('credential_resolver must return SwitchCredentials or None')
                # Normalize positional password arguments before overriding them.
                if len(args) >= (2 if kind == 'su' else 1):
                    args = list(args)
                    args[1 if kind == 'su' else 0] = credential.password
                    kwargs.pop('password', None)
                else:
                    kwargs['password'] = credential.password
                supplied = True
            if not supplied and not self._terminal:
                raise CredentialsRequiredError('provide credentials or explicit password=None')
            if not supplied:
                kwargs['password'] = self.password_func(kind + ' password: ')
            self._console_layer(kind, *args, **kwargs)
        except BaseException as error:
            if self._observer:
                self._observer(SwitchOutcome(request, False, self.environments[-1],
                                             type(error).__name__))
            raise
        if self._observer:
            self._observer(SwitchOutcome(request, True, self.environments[-1]))

    def _console_layer(self, kind, *args, **kwargs):
        self._check(idle=True)
        layer = self.current
        if layer.kind == 'program':
            raise RuntimeError('leave the interactive program before entering another layer')
        with ExitStack() as resources:
            wrapper = getattr(layer.console, kind)(*args, **kwargs)
            console = resources.enter_context(wrapper)
            self._push(resources, layer.session, console,
                       'program' if kind == 'enter' else kind, layer.host,
                       program=kind == 'enter')
            if kind == 'enter':
                self.current.exit_command = wrapper.exit_command
        if kind == 'enter':
            self._drain_program()

        self._state = 'running' if kind == 'enter' else 'completed'
        self._last_result, self._error_type = None, None
        if kind == 'enter':
            self._program_started = time.monotonic()

    def connect(self, *args, **kwargs):
        self._check(idle=True)
        layer = self.current
        if layer.kind not in ('local', 'ssh'):
            raise RuntimeError('leave the current sudo/su/shell/program layer before connect(); SSH credentials belong to the connection Session')
        with ExitStack() as resources:
            remote = layer.session.connect(*args, **kwargs)
            resources.callback(remote.close, strict=True)
            resources.enter_context(remote)
            wrapper = remote.shell('bash')
            wrapper.channel.dump2sys = (0, 0)
            shell = resources.enter_context(wrapper)
            self._push(resources, remote, shell, 'ssh', remote.host or '?')

    def _discard_failed_layers(self):
        if any(layer.console.channel.closed or
               getattr(layer.console.channel, '_state', None) in ('failed', 'closed')
               for layer in self.layers):
            self._uncertain = True
            self._state = 'failed'
            self._reuse = 'unknown'

    def _command(self, line, *, timeout=None, capture_limit=8 * 1024 * 1024,
                 stop_timeout=3):
        try:
            if self.current.kind == 'program':
                return self.send_input(line).result
            # Managed foreground jobs retain shell state, stream output and recover
            # the parent shell after Ctrl-C. Completion is never inferred from silence.
            job = self.current.console.start(line, timeout=timeout, capture_limit=capture_limit,
                                             stop_timeout=stop_timeout, check=False)
            positions = [0, 0]
            def drain():
                for index, (text, stream) in enumerate(((job.stdout, self._stdout),
                                                       (job.stderr, self._stderr))):
                    self._write(text[positions[index]:], stream)
                    positions[index] = len(text)
            try:
                while not job.done:
                    drain()
                    time.sleep(0.03)
                result = job.wait()
            except KeyboardInterrupt:
                result = job.stop()
                self._write('\nKeyboardInterrupt\n', self._stderr)
            finally:
                drain()
            self.namespace['result'] = self.current.result = result
            if result.exitcode not in (0, None):
                self._write(f'[exit {result.exitcode}]\n', self._stderr)
            if result.stdout_truncated or result.stderr_truncated:
                self._write('[output capture limit reached]\n', self._stderr)
        except Exception as error:
            self._last_result = getattr(error, 'result', None)
            if self._last_result is not None and self._last_result.termination_status != 'confirmed':
                self._uncertain, self._reuse = True, 'unknown'
            raise
        self._last_result = result
        if result is not None and result.termination_status != 'confirmed':
            self._uncertain, self._reuse = True, 'unknown'
        if result is not None:
            self._state = ('completed' if result.stop_reason == 'completed'
                           and result.exitcode == 0 else 'failed')
        return result

    def _update(self, *, consume=True):
        output = []
        for buffer in self._capture:
            output.append(buffer.getvalue())
            if consume:
                buffer.seek(0)
                buffer.truncate(0)
        return ConsoleUpdate(self._state, *output, self._last_result,
                             self._error_type, self._reuse)

    def submit(self, line):
        """Evaluate one Python/dollar line, returning a structured update.

        Shell dollar commands block until completion; use start_command for polling.
        Operation errors are reported by safe type, without source/error text.
        """
        self._check(idle=True)
        if self.done:
            return self._update()
        if (self.current.kind == 'program' and not line.lstrip().startswith('$.')
                and line.strip() not in (':status', ':error', ':traceback')):
            if self._bare_helper(line) is None:
                try:
                    return self.send_input(line)
                except KeyboardInterrupt:
                    return self.interrupt()
        self._state, self._error_type, self._last_result = 'completed', None, None
        self.python.last_error = None
        self._submitting = True
        try:
            self._submit_line(line)
        except ConsoleCleanupError:
            raise
        except (Exception, KeyboardInterrupt, SystemExit) as error:
            self.namespace['error'] = error
            self._state, self._error_type = 'failed', type(error).__name__
            self._write(f'{type(error).__name__}: operation failed; use :error or :traceback for details.\n', self._stderr)
        finally:
            self._submitting = False
        if self.python.last_error is not None:
            self._state, self._error_type = 'failed', self.python.last_error
        elif self.more:
            self._state = 'incomplete'
        if self.done:
            self._state = 'closed' if self._reuse != 'unknown' else 'failed'
        return self._update()

    def start(self, command, *, timeout=60, stop_timeout=3,
              capture_limit=1024 * 1024, check=False):
        """Start and track a foreground job, including prompt-level $.start()."""
        self._check(idle=True)
        if self.more:
            raise RuntimeError('finish or interrupt incomplete Python input first')
        self._job = self.current.console.start(command, timeout=timeout,
                                              stop_timeout=stop_timeout,
                                              capture_limit=capture_limit, check=check)
        self._job_positions = [0, 0]
        self._state, self._error_type, self._last_result = 'running', None, None
        return self._job

    def start_command(self, command, *, timeout=60, stop_timeout=3,
                      capture_limit=1024 * 1024):
        """Start a foreground shell command and return its first update."""
        self.start(command, timeout=timeout, stop_timeout=stop_timeout,
                   capture_limit=capture_limit, check=False)
        return self.poll()

    def _drain_job(self):
        for index, (text, stream) in enumerate(((self._job.stdout, self._stdout),
                                               (self._job.stderr, self._stderr))):
            self._write(text[self._job_positions[index]:], stream)
            self._job_positions[index] = len(text)

    def _finish_job(self, *, stop=False):
        job = self._job
        try:
            self._last_result = job.stop() if stop else job.wait()
            self._state = ('completed' if self._last_result.stop_reason == 'completed'
                           and self._last_result.exitcode == 0 else 'failed')
        except Exception as error:
            self._last_result = getattr(error, 'result', None)
            self._state, self._error_type = 'failed', type(error).__name__
            if self._last_result is None or self._last_result.termination_status != 'confirmed':
                self._uncertain = True
                self._reuse = 'unknown'
        finally:
            self._drain_job()
            self._job = None
        if self._last_result is not None:
            self.namespace['result'] = self.current.result = self._last_result
            if self._last_result.termination_status != 'confirmed':
                self._uncertain, self._reuse = True, 'unknown'

    def poll(self):
        """Return available output; never wait for a running command."""
        self._poll()
        return self._update()

    def _poll(self):
        self._check()
        if self._job is not None:
            self._drain_job()
            if self._job.done:
                self._finish_job()
        elif self.layers and self.current.kind == 'program':
            channel = self.current.console.channel
            texts = (str(channel._stdout), str(channel._stderr))
            parent = channel.prompts[-2] if len(channel.prompts) > 1 else None
            prompt = channel.prompt
            if isinstance(parent, str) and parent and parent != prompt and any(parent in text for text in texts):
                channel._mark_interactive_layer_exited(channel.executing_lock)
                self._drain_program()
                self.leave()
            else:
                if isinstance(prompt, str) and prompt and any(prompt in text for text in texts):
                    self._state = 'waiting_input'
                self._drain_program()
        self._discard_failed_layers()

    def send_input(self, text, *, newline=True, timeout=1):
        """Send a raw write or one line to an enter() program."""
        self._send_input(text, newline=newline, timeout=timeout)
        return self._update()

    def input(self, text=None, timeout=60, *, secret=False):
        """Send a line, or read a hidden reply with secret=True in an enter() layer.

        Hidden input bypasses Python evaluation and readline history and returns
        None. Embedded callers must supply password_func. Remote output is not
        redacted: the receiving program must also avoid echoing secrets.
        """
        self._check(idle=True)
        if not isinstance(secret, bool):
            raise TypeError('secret must be bool')
        if not secret:
            if not isinstance(text, str):
                raise TypeError('input text must be str')
            return self.current.console.input(text, timeout=timeout)
        if text is not None:
            raise ValueError('secret input reads from password_func; do not supply text')
        if self.current.kind != 'program':
            raise RuntimeError('secret input requires an enter() program')
        self._poll()
        if self.current.kind != 'program':
            return None
        try:
            text = self.password_func('Secret input (hidden): ')
            if not isinstance(text, str):
                raise TypeError('password_func must return str')
            if '\n' in text or '\r' in text:
                raise ValueError('secret input must be a single line')
            self._send_input(text, timeout=timeout)
        finally:
            text = None
        return None

    def _send_input(self, text, *, newline=True, timeout=1):
        self._check()
        if self._job is not None:
            raise RuntimeError('shell jobs do not accept input; use enter() for an interactive program')
        if self.current.kind != 'program':
            raise RuntimeError('input requires a running job or enter() program')
        # Drain pending output before input() replaces the capture buffers.
        # A delayed parent prompt also means this input must not reach the shell.
        self._poll()
        if not self.layers or self.current.kind != 'program':
            return
        self.current.input_tail = ''
        self.current.secret_pending = False
        self._last_result, self._error_type = None, None
        outcome = None
        try:
            if newline:
                outcome = self.current.console.input(text, timeout=timeout)
            else:
                self.current.console.send(text)
            self._state = 'waiting_input' if outcome == 'prompt' else 'running'
        except TimeoutError as error:
            self.namespace['error'] = error
            self._state, self._error_type = 'running', 'TimeoutError'
        finally:
            self._drain_program()
        if outcome == 'exited':
            self.leave()
        self._discard_failed_layers()

    def _interrupt(self):
        self.python.resetbuffer()
        self.more = False
        if self.layers and self.current.kind == 'program':
            self._program_control('\x03')
        else:
            self._write('\nKeyboardInterrupt\n', self._stderr)
            self._state = 'ready'
        self._error_type = 'KeyboardInterrupt'

    def interrupt(self):
        self._check()
        if self._job is not None:
            self._finish_job(stop=True)
        else:
            self._interrupt()
        return self._update()

    def eof(self):
        self._check(idle=True)
        self._eof()
        return self._update()

    def leave(self):
        self._check(idle=True)
        if len(self.layers) == 1:
            return self.close()
        layer = self.current
        program = layer.kind == 'program'
        output = (str(layer.console.channel._stdout), str(layer.console.channel._stderr)) if program else None
        try:
            self._release_layer()
            if layer.console.channel._failure is not None:
                raise RuntimeError('environment recovery failed')
            if program:
                status = self.current.console.exitcode
                self._last_result = CommandResult(*output, status, layer.session.host, time.monotonic() - self._program_started, '<interactive>')
                self.namespace['result'] = self.current.result = self._last_result
                self._state = 'completed' if status == 0 else 'failed'
        except BaseException:
            self._uncertain, self._reuse = True, 'unknown'
            raise ConsoleCleanupError('layer cleanup failed; Session reuse is unknown') from None

    def close(self):
        self._check()
        if self.done:
            if self._cleanup_error:
                raise self._cleanup_error
            return self._update()
        failures = []
        if self._job is not None:
            self._finish_job(stop=True)
        while self.layers:
            layer = self.current
            if layer.console.channel._failure is not None:
                self._uncertain = True
            try:
                self._release_layer()
                if layer.console.channel._failure is not None:
                    self._uncertain = True
            except BaseException as error:
                failures.append(type(error).__name__)
        self.done = True
        try:
            if self._ownership == 'owned':
                self._session.close(strict=True)
                self._reuse = 'closed'
            elif not failures and not self._uncertain:
                self._session.exec_command('true', check=True, command_timeout=3)
                self._reuse = 'confirmed'
        except BaseException as error:
            failures.append(type(error).__name__)
        if failures or self._uncertain:
            self._state, self._reuse = 'failed', 'unknown'
            self._cleanup_error = ConsoleCleanupError('console cleanup or Session recovery unconfirmed')
            raise self._cleanup_error from None
        self._state = 'closed'
        return self._update(consume=not self._submitting)

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.close()
        except BaseException as cleanup:
            if exc_value is not None:
                raise BaseExceptionGroup('host operation and console cleanup failed',
                                         [exc_value, cleanup]) from None
            raise
        return False



HELP = '''Input is Python with SSHScript dollar syntax; variables persist between inputs.
$hostname executes a command in the current persistent Bash shell.
print($.stdout), $.stderr and $.exitcode inspect the last dollar-command result.
$.connect(host, **options) connects and automatically enters a persistent shell.
$.sudo(password=...), $.su("user", password=...) enter identity layers.
$.shell("bash") enters a nested shell.
$.enter("python3 -q", prompt=">>>", exit="quit()") enters a text program.
Password prompts in enter() use hidden input when recognized.
$.input(secret=True) reads and sends one hidden reply for an unrecognized prompt.
exit / exit() / $.exit() leave one layer; at the local root they end the console.
$.exit("quit") sends a program exit command and waits for its return.
Without an explicit or configured exit command, enter() stays open with a reminder.
Use Python multiline blocks with a blank line to execute, just like a Python REPL.
Python names: session (connection), console (current identity), result, error, getpass.
$.run(source) / $.run_file(path) execute scripts; $.stop() ends only that script.
help / help() show this guide; help(object) shows Python object documentation.
:error shows the last error message; :traceback shows its full traceback, also in enter().
quit / quit() close all layers. $.exit() is a console-only operation.
:status shows the environment stack. Ctrl-C cancels current input or execution.
Ctrl-D at the Python prompt closes the console. In enter(), Ctrl-C/D go to the program.
Inside enter(), plain input goes to that program; $. expressions remain controls.
No input history is persisted. Full-screen programs are not supported.'''



def main(argv=None):
    parser = argparse.ArgumentParser(prog='sshscript console', description=HELP, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('host', nargs='?')
    parser.add_argument('--username')
    parser.add_argument('--port', type=int)
    parser.add_argument('--parent-key-filename')
    parser.add_argument('--key-filename')
    parser.add_argument('--proxy-command')
    parser.add_argument('--proxy-jump')
    parser.add_argument('--timeout', type=float)
    parser.add_argument('--ssh-config')
    parser.add_argument('--known-hosts-source', choices=('local', 'parent', 'chain'))
    parser.add_argument('--known-hosts-path')
    parser.add_argument('--ask-pass', action='store_true')
    args = parser.parse_args(argv)
    options = {name: value for name, value in vars(args).items()
               if name not in ('host', 'ask_pass', 'known_hosts_path') and value is not None}
    if args.host is None and (options or args.ask_pass):
        parser.error('connection options require a host')
    session = Session()
    try:
        if args.known_hosts_path is not None:
            session.set(known_hosts_path=args.known_hosts_path)
        with Console(session, ownership='owned', terminal=True) as console:
            if args.ask_pass:
                options['password'] = console.password_func('SSH password: ')
            if args.host is not None:
                console.connect(args.host, **options)
            console.interact()
    finally:
        session.close(strict=True)
    return 0
