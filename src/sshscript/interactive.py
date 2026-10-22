"""Persistent text console for humans and agents using a retained terminal session."""
import argparse
import ast
import builtins
import code
from io import StringIO
import tokenize
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from dataclasses import dataclass
from getpass import getpass
import sys
import time
import subprocess

if __package__:
    from . import dollarparser, tokenparser, patching
    from .session import Session
else:
    import dollarparser, tokenparser, patching
    from session import Session


class _LeaveLayer(BaseException):
    pass


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
        except (SyntaxError, OverflowError, ValueError):
            self.cell += 1
            self.showsyntaxerror(filename)
            return False
        self.cell += 1
        self.runcode(compiled)
        return False

    def runcode(self, code_object):
        try:
            exec(code_object, self.locals)
        except (_LeaveLayer, _QuitConsole, SystemExit, KeyboardInterrupt):
            raise
        except BaseException as error:
            self.locals['error'] = error
            if isinstance(error, NameError):
                self.write(f'{type(error).__name__}: {error}\n')
            else:
                # Do not echo credential-bearing source or arbitrary server text.
                self.write(f'{type(error).__name__}: operation failed; inspect error for details.\n')


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


class InteractiveConsole:
    """Own a stack of connection/console contexts and a persistent Python namespace.

    All context entry and exit occurs on the calling thread. No input history is
    persisted. Connections under sudo/su are rejected rather than implying that
    the SSH Session has adopted the console's effective identity or key files.
    """
    def __init__(self, *, stdout=None, stderr=None, input_func=None,
                 password_func=None, session_factory=Session):
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr
        self.input_func = input_func or input
        self.password_func = password_func or getpass
        self.session_factory = session_factory
        self.layers = []
        self.namespace = {'__name__': '__console__', 'getpass': self.password_func,
                          'control': self, '_console_control_': self,
                          'patching': patching, 'result': None, 'error': None}
        self._helpers = {'help': self.help, 'exit': self._exit_layer, 'quit': self.quit}
        self.namespace.update(self._helpers)
        self.python = _PythonConsole(self.namespace)
        self.more = False
        self.done = False

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

    def open(self, host=None, **options):
        if self.layers or self.done:
            raise RuntimeError('console has already been opened')
        with ExitStack() as resources:
            local = self.session_factory()
            resources.callback(local.close, strict=True)
            resources.enter_context(local)
            local.set(verbose=False, verbose_stderr=False, check=False)
            shell = resources.enter_context(local.shell('bash'))
            self._push(resources, local, shell, 'local', 'local')
        try:
            if host is not None:
                self.connect(host, **options)
        except BaseException:
            self.close()
            raise
        return self

    def connect(self, *args, **kwargs):
        layer = self.current
        if layer.kind not in ('local', 'ssh'):
            raise RuntimeError('leave the current sudo/su/shell/program layer before connect(); SSH credentials belong to the connection Session')
        with ExitStack() as resources:
            remote = layer.session.connect(*args, **kwargs)
            resources.callback(remote.close, strict=True)
            resources.enter_context(remote)
            remote.set(verbose=False, verbose_stderr=False, check=False)
            shell = resources.enter_context(remote.shell('bash'))
            self._push(resources, remote, shell, 'ssh', remote.host or '?')

    def _console_layer(self, kind, *args, **kwargs):
        layer = self.current
        if layer.kind == 'program':
            raise RuntimeError('leave the interactive program before entering another layer')
        with ExitStack() as resources:
            console = resources.enter_context(getattr(layer.console, kind)(*args, **kwargs))
            self._push(resources, layer.session, console,
                       'program' if kind == 'enter' else kind, layer.host,
                       program=kind == 'enter')
        if kind == 'enter':
            self._drain_program()

    def shell(self, *args, **kwargs):
        self._console_layer('shell', *args, **kwargs)

    def _identity_layer(self, kind, *args, **kwargs):
        if 'password' not in kwargs:
            # su's first positional argument is username; sudo's is password.
            supplied_positionally = len(args) >= (2 if kind == 'su' else 1)
            if not supplied_positionally:
                if self.password_func is getpass and not sys.stdin.isatty():
                    raise ValueError('provide password explicitly (password=None for passwordless authentication) when stdin is not a terminal')
                kwargs['password'] = self.password_func(kind + ' password: ')
        self._console_layer(kind, *args, **kwargs)

    def sudo(self, *args, **kwargs):
        self._identity_layer('sudo', *args, **kwargs)

    def su(self, *args, **kwargs):
        self._identity_layer('su', *args, **kwargs)

    def enter(self, *args, **kwargs):
        """Explicitly enter a text program; configure its prompt and exit text."""
        self._console_layer('enter', *args, **kwargs)

    def _exit_layer(self):
        raise _LeaveLayer()

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
        if name in ('send', 'input', 'expect', 'start'):
            return getattr(self.current.console, name)
        if name in ('stdout', 'stderr', 'exitcode'):
            if self.current.kind == 'program':
                return getattr(self.current.console, name)
            result = self.current.result
            return getattr(result, name) if result is not None else (None if name == 'exitcode' else '')
        raise AttributeError(name)

    def leave(self):
        layer = self.layers.pop()
        try:
            layer.resources.close()
        finally:
            if self.layers:
                self._refresh()
            else:
                self.done = True
                self.namespace.update(session=None, console=None)

    def close(self):
        failures = []
        while self.layers:
            try:
                self.leave()
            except BaseException as error:
                failures.append(error)
        self.done = True
        if failures:
            raise BaseExceptionGroup('console cleanup failed', failures)

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
        if (enabled and result is not None and result.stop_reason == 'completed'
                and result.exitcode != 0):
            error = subprocess.CalledProcessError(result.exitcode, command,
                                                 output=result.stdout, stderr=result.stderr)
            error.result = result
            raise error
        return result

    def _command(self, line, *, timeout=None, capture_limit=8 * 1024 * 1024,
                 stop_timeout=3):
        if self.current.kind == 'program':
            outcome = self.current.console.input(line)
            self._drain_program()
            if outcome == 'exited':
                self.leave()
            return
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
            positions.append(len(text))
        layer.program_buffers = buffers
        layer.program_positions = tuple(positions)

    def _program_control(self, character):
        """Send Ctrl-C/D without a newline and observe the program's real prompts."""
        self._drain_program()
        channel = self.current.console.channel
        try:
            outcome = channel._input_text(character, timeout=2, append_newline=False)
        except TimeoutError:
            # A program may ignore the control byte. Do not invent an exit.
            outcome = None
        self._drain_program()
        if outcome == 'exited':
            self.leave()

    def _interrupt(self):
        self.python.resetbuffer()
        self.more = False
        if self.layers and self.current.kind == 'program':
            self._program_control('\x03')
        else:
            self._write('\nKeyboardInterrupt\n', self._stderr)

    def _eof(self):
        if self.layers and self.current.kind == 'program':
            self._program_control('\x04')
        else:
            self.python.resetbuffer()
            self.more = False
            self.close()

    def _discard_failed_layers(self):
        while self.layers:
            channel = self.current.console.channel
            if not channel.closed and getattr(channel, '_state', None) not in ('failed', 'closed'):
                break
            self._write('Current shell is unavailable; leaving its environment.\n', self._stderr)
            try:
                self.leave()
            except Exception as error:
                self._write('Cleanup failed: ' + type(error).__name__ + '\n', self._stderr)

    def execute(self, line):
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
            elif not self.more and line.strip() == ':quit':
                self.close()
            elif not self.more and line.strip() == ':help':
                self._write(HELP + '\n', self._stdout)
            elif not self.more and line.strip() == ':status':
                for layer in self.layers:
                    self._write(f'{layer.kind}: {layer.host} [{layer.user}]\n', self._stdout)
                self._write('Transfers and SSH credentials use the connection account.\n', self._stdout)
            elif (not self.more and self.current.kind == 'program'
                  and not line.lstrip().startswith('$.')):
                self._command(line)
            else:
                with redirect_stdout(self._stdout), redirect_stderr(self._stderr):
                    self.more = self.python.push(line)
        except _QuitConsole:
            self.python.resetbuffer()
            self.more = False
            self.close()
        except KeyboardInterrupt:
            self._interrupt()
        except _LeaveLayer:
            self.python.resetbuffer()
            self.more = False
            self.leave()
        except SystemExit as error:
            self.python.resetbuffer()
            self.more = False
            self._write(f'Python/script exited ({error.code}); console remains open.\n', self._stderr)
        finally:
            self._discard_failed_layers()

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
                    line = self.input_func(self.prompt)
                except EOFError:
                    self._eof()
                    continue
                except KeyboardInterrupt:
                    self._interrupt()
                    continue
                try:
                    self.execute(line)
                except KeyboardInterrupt:
                    self._interrupt()
                except Exception as error:
                    # Avoid echoing credential-bearing expressions or arbitrary
                    # server error text; the original exception is available as error.
                    self.namespace['error'] = error
                    self._write('Operation failed (' + type(error).__name__ + '). Use :status or inspect error.\n', self._stderr)
        finally:
            self.close()


HELP = '''Input is Python with SSHScript dollar syntax; variables persist between inputs.
$hostname executes a command in the current persistent Bash shell.
print($.stdout), $.stderr and $.exitcode inspect the last dollar-command result.
$.connect(host, **options) connects and automatically enters a persistent shell.
$.sudo(password=...), $.su("user", password=...) enter identity layers.
$.shell("bash") enters a nested shell.
$.enter("python3 -q", prompt=">>>", exit="quit()") enters a text program.
exit / exit() leave one layer; at the local root they end the console.
Use Python multiline blocks with a blank line to execute, just like a Python REPL.
Python names: session (connection), console (current identity), result, error, getpass.
$.run(source) / $.run_file(path) execute scripts; $.stop() ends only that script.
help / help() show this guide; help(object) shows Python object documentation.
quit / quit() close all layers. $.exit() is not available.
:status shows the environment stack. Ctrl-C cancels current input or execution.
Ctrl-D at the Python prompt closes the console. In enter(), Ctrl-C/D go to the program.
:help and :quit remain aliases.
Inside enter(), plain input goes to that program; $. expressions remain controls.
No input history is persisted. Full-screen programs are not supported in this preview.'''



def main(argv=None):
    parser = argparse.ArgumentParser(prog='sshscript console', description=HELP,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('host', nargs='?')
    parser.add_argument('--username')
    parser.add_argument('--port', type=int)
    parser.add_argument('--pkey-path')
    parser.add_argument('--timeout', type=float)
    parser.add_argument('--ssh-config')
    parser.add_argument('--known-hosts', choices=('local', 'parent', 'chain'))
    parser.add_argument('--known-hosts-path')
    parser.add_argument('--ask-pass', action='store_true')
    args = parser.parse_args(argv)
    options = {name: value for name, value in vars(args).items()
               if name not in ('host', 'ask_pass', 'known_hosts_path') and value is not None}
    if args.host is None and (options or args.ask_pass):
        parser.error('connection options require a host')
    console = InteractiveConsole()
    try:
        console.open()
        if args.known_hosts_path is not None:
            console.current.session.set(known_hosts_path=args.known_hosts_path)
        if args.ask_pass:
            options['password'] = getpass('SSH password: ')
        if args.host is not None:
            console.connect(args.host, **options)
        console.interact()
    finally:
        console.close()
    return 0
