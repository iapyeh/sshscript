"""Public regressions for retained console state and script completion boundaries."""
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
from unittest.mock import patch

import sshscript
import patching
from interactive import Console
from scriptcontrol import ScriptResult
from session import Session


class _CLITestCase(unittest.TestCase):
    def assert_no_unexpected_stderr(self, stderr):
        # Match the existing module CLI tests: only Paramiko's known TripleDES
        # dependency deprecations are allowed; other diagnostics remain errors.
        diagnostic = re.sub(
            r'(?m)^.*[/\\]paramiko[/\\](?:pkey|transport)\.py:\d+: '
            r'CryptographyDeprecationWarning: TripleDES[^\n]*\n[ \t]+[^\n]*\n',
            '', stderr)
        self.assertEqual(diagnostic, '')


class ScriptControlTests(_CLITestCase):
    def test_stop_returns_namespace_and_runs_finally_without_exception_catch(self):
        result = sshscript.run_script('''before = 1
try:
    $.stop(7, "nothing to do")
except Exception:
    intercepted = True
finally:
    cleaned = True
after = 2
''')
        self.assertIsInstance(result, ScriptResult)
        self.assertEqual((result.exitcode, result.stopped, result.message), (7, True, 'nothing to do'))
        self.assertTrue(result['cleaned'])
        self.assertNotIn('intercepted', result)
        self.assertNotIn('after', result)

    def test_stop_inside_shell_cleans_context(self):
        session = Session()
        self.addCleanup(session.close)
        before = patching.get_thread_stack().snapshot()
        result = session.run('''with $.shell("bash", get_pty=False):
    $printf ready
    $.stop()
after = True
''')
        self.assertTrue(result.stopped)
        self.assertNotIn('after', result)
        self.assertEqual(patching.get_thread_stack().snapshot(), before)
        self.assertEqual(session.exec_command('printf alive').stdout, 'alive')

    def test_nested_run_stops_only_child(self):
        result = sshscript.run_script('''child = sshscript.run_script("value=42\\n$.stop()\\nmissing=True", {})
continued = True
''', {'sshscript': sshscript})
        self.assertTrue(result['continued'])
        self.assertTrue(result['child'].stopped)
        self.assertEqual(result['child']['value'], 42)
        self.assertNotIn('missing', result['child'])
        self.assertFalse(result.stopped)

    def test_nested_run_on_same_session_has_its_own_stop_boundary(self):
        session = Session()
        self.addCleanup(session.close)
        result = session.run('child = session.run("value=42\\n$.stop(3)", {})\ncontinued=True', {'session': session})
        self.assertTrue(result['continued'])
        self.assertEqual(result['child'].exitcode, 3)
        self.assertFalse(result.stopped)

    def test_file_and_cli_preserve_status_without_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'stop.spy')
            path.write_text('$.stop(23)\nraise RuntimeError("unreachable")\n')
            self.assertEqual(sshscript.run_file(path), 23)
            cli = subprocess.run([sys.executable, str(Path(sshscript.__file__)), str(path)],
                                 capture_output=True, text=True, timeout=20)
            self.assertEqual(cli.returncode, 23)
            self.assert_no_unexpected_stderr(cli.stderr)

    def test_stop_in_imported_spy_finishes_only_module(self):
        with tempfile.TemporaryDirectory() as folder:
            name = 'sshscript_stopped_module_fixture'
            Path(folder, name + '.spy').write_text('value=42\n$.stop()\nmissing=True\n')
            sys.path.insert(0, folder)
            try:
                with sshscript.spy_imports():
                    result = sshscript.run_script('import ' + name + '\ncontinued=True')
                self.assertTrue(result['continued'])
                self.assertEqual(sys.modules[name].value, 42)
                self.assertFalse(hasattr(sys.modules[name], 'missing'))
            finally:
                sys.path.remove(folder)
                sys.modules.pop(name, None)

    def test_exit_is_not_a_script_exit_and_python_systemexit_propagates(self):
        with self.assertRaises(AttributeError):
            sshscript.run_script('$.exit()')
        with self.assertRaises(SystemExit) as caught:
            sshscript.run_script('import sys\nsys.exit(19)')
        self.assertEqual(caught.exception.code, 19)
        with self.assertRaisesRegex(RuntimeError, 'running script'):
            Session().stop()

    def test_old_break_is_removed(self):
        with self.assertRaises((SyntaxError, AttributeError)):
            sshscript.run_script('$.break()')


class InteractiveTests(_CLITestCase):
    def setUp(self):
        self.enterContext(warnings.catch_warnings())
        warnings.filterwarnings('ignore', message="'get_child_watcher' is deprecated.*",
                                category=DeprecationWarning, module=r'asyncio\.events')

    def open_console(self):
        output, errors = io.StringIO(), io.StringIO()
        console = Console(Session(), ownership='owned', terminal=True, stdout=output, stderr=errors)
        self.addCleanup(console.close)
        return console, output, errors

    def test_directory_environment_variables_python_and_failure_survive_inputs(self):
        console, output, errors = self.open_console()
        with tempfile.TemporaryDirectory() as folder:
            import shlex
            console.submit('$cd ' + shlex.quote(folder))
            console.submit('$export CONSOLE_FIXTURE=retained')
            console.submit('$pwd; printf "%s" "$CONSOLE_FIXTURE"')
            self.assertIn(folder, output.getvalue())
            self.assertIn('retained', output.getvalue())
            console.submit('$false')
            self.assertEqual(console.namespace['result'].exitcode, 1)
            self.assertIn('[exit 1]', errors.getvalue())
            console.submit('options = {"port": 2222}')
            console.submit('for index in range(2):')
            console.submit('    options["count"] = index')
            console.submit('')
            console.submit('$printf after-failure')
            self.assertIn('after-failure', output.getvalue())
            self.assertEqual(console.namespace['options'], {'port': 2222, 'count': 1})
            console.submit('print(options["port"])')
            self.assertIn('2222', output.getvalue())

    def test_bare_name_is_python_and_never_an_implicit_shell_command(self):
        console, output, errors = self.open_console()
        with patch.object(console, 'exec_command') as execute:
            console.submit('hostname')
            self.assertIn('NameError', errors.getvalue())
            console.submit('hostname = "a Python variable"')
            console.submit('hostname')
            execute.assert_not_called()
        self.assertIn('a Python variable', output.getvalue())

    def test_dollar_command_result_is_available_inside_python_expressions(self):
        console, output, errors = self.open_console()
        console.submit('$printf host-fixture')
        self.assertEqual(output.getvalue(), 'host-fixture')
        console.submit('print($.stdout)')
        console.submit('hostname = $.stdout.strip()')
        console.submit('status = $.exitcode')
        self.assertEqual(console.namespace['hostname'], 'host-fixture')
        self.assertEqual(console.namespace['status'], 0)
        console.submit('message = f"host={$.stdout.strip()}"')
        self.assertEqual(console.namespace['message'], 'host=host-fixture')
        console.submit('out, err, status = $printf another-host')
        self.assertEqual((console.namespace['out'], console.namespace['err'], console.namespace['status']),
                         ('another-host', '', 0))
        console.submit('literal = "$.stdout is text, not evaluation"')
        self.assertEqual(console.namespace['literal'], '$.stdout is text, not evaluation')
        self.assertEqual(errors.getvalue(), '')

    def test_dollar_commands_in_python_multiline_loop_and_function(self):
        console, output, errors = self.open_console()
        for line in ['for index in range(2):', '    $f"echo item-{index}"', '']:
            console.submit(line)
        self.assertIn('item-0', output.getvalue())
        self.assertIn('item-1', output.getvalue())
        for line in ['def read_host():', '    $printf function-host', '    return $.stdout', '']:
            console.submit(line)
        console.submit('saved = read_host()')
        self.assertEqual(console.namespace['saved'], 'function-host')
        self.assertFalse(console.more)
        self.assertEqual(errors.getvalue(), '')

    def test_multiline_dollar_connection_waits_for_complete_expression(self):
        console, _, errors = self.open_console()
        parent = console.current
        remote = Session()
        self.addCleanup(remote.close)
        console.namespace['host'] = 'fixture'
        with patch.object(parent.session, 'connect', return_value=remote) as connect:
            console.submit('$.connect(')
            self.assertTrue(console.more)
            connect.assert_not_called()
            console.submit('    host,')
            self.assertTrue(console.more)
            console.submit('    username="ops",')
            console.submit(')')
        connect.assert_called_once_with('fixture', username='ops')
        self.assertFalse(console.more)
        self.assertEqual(len(console.layers), 2)
        console.submit('exit()')
        self.assertEqual(errors.getvalue(), '')

    def test_syntax_error_recovers_for_next_input(self):
        console, _, errors = self.open_console()
        console.submit('$.stdout + )')
        self.assertFalse(console.more)
        self.assertIn('SyntaxError', errors.getvalue())
        console.submit('value = 42')
        self.assertEqual(console.namespace['value'], 42)

    def test_lexical_with_uses_normal_spy_scope_and_restores_stack(self):
        console, output, errors = self.open_console()
        original = console.current
        stack = patching.get_thread_stack().snapshot()
        for line in ['with $.shell("bash"):', '    $printf lexical-host', '    saved = str($.stdout)', '']:
            console.submit(line)
        self.assertEqual(console.namespace['saved'], 'lexical-host')
        self.assertIs(console.current, original)
        self.assertEqual(patching.get_thread_stack().snapshot(), stack)
        self.assertEqual(errors.getvalue(), '')

    def test_program_exit_returns_to_python_console_without_extra_exit(self):
        console, output, errors = self.open_console()
        original = console.current
        import shlex
        console.submit('$.enter(' + repr(shlex.quote(sys.executable) + ' -q -u') + ', prompt=">>>", exit="quit()")')
        console.submit('raise SystemExit')
        self.assertIs(console.current, original)
        console.submit('value = 42')
        self.assertEqual(console.namespace['value'], 42)
        self.assertEqual(errors.getvalue(), '')

    def test_nested_shell_exit_restores_parent_and_root_exit_closes(self):
        console, output, errors = self.open_console()
        original = console.current
        original_stack = patching.get_thread_stack().snapshot()
        console.submit('$.shell("bash")')
        self.assertEqual(len(console.layers), 2)
        console.submit('exit()')
        self.assertIs(console.current, original)
        self.assertEqual(patching.get_thread_stack().snapshot(), original_stack)
        console.submit('$printf parent-restored')
        self.assertIn('parent-restored', output.getvalue())
        console.submit('exit()')
        self.assertTrue(console.done)
        self.assertTrue(original.session.closed)
        console.close()

    def test_session_and_wrapper_exit_are_removed_in_console(self):
        console, _, _ = self.open_console()
        console.submit('$.shell("bash")')
        current = console.current
        for source in ('session.exit()', 'console.exit()'):
            console.submit(source)
            self.assertIsInstance(console.namespace['error'], AttributeError)
            self.assertIs(console.current, current)
            self.assertEqual(len(console.layers), 2)
        self.assertFalse(console.more)

    def test_connect_evaluates_literals_variables_kwargs_and_groups_shell(self):
        console, _, _ = self.open_console()
        parent = console.current
        remote = Session()
        self.addCleanup(remote.close)
        console.namespace.update(host='fixture', options={'username': 'ops', 'port': 2222})
        with patch.object(parent.session, 'connect', return_value=remote) as connect:
            console.submit('$.connect(host, password="literal", **options)')
        connect.assert_called_once_with('fixture', password='literal', username='ops', port=2222)
        self.assertEqual(len(console.layers), 2)
        console.submit('exit()')
        self.assertIs(console.current, parent)
        self.assertTrue(remote.closed)
        self.assertFalse(parent.session.closed)

    def test_failed_connection_shell_entry_rolls_back(self):
        console, _, _ = self.open_console()
        parent = console.current
        remote = Session()
        with patch.object(parent.session, 'connect', return_value=remote), \
             patch.object(remote, 'shell', side_effect=RuntimeError('fixture shell failure')):
            console.submit('$.connect("fixture")')
            self.assertIsInstance(console.namespace['error'], RuntimeError)
        self.assertTrue(remote.closed)
        self.assertIs(console.current, parent)
        console.submit('$true')

    def test_identity_layers_route_parameters_and_unwind(self):
        # Use real shell layers as credential-free stand-ins for auth; native
        # su/sudo handshakes remain covered by the dedicated native matrix.
        console, _, _ = self.open_console()
        original = console.current
        with patch.object(original.console, 'sudo', side_effect=lambda **kw: original.console.shell('bash')) as sudo:
            console.submit('$.sudo(password=None, username="fixture")')
        sudo.assert_called_once_with(password=None, username='fixture')
        self.assertEqual(console.current.kind, 'sudo')
        console.submit('$.connect("other")')
        self.assertIsInstance(console.namespace['error'], RuntimeError)
        self.assertIn('credentials', str(console.namespace['error']))
        with patch.object(console.current.console, 'su', side_effect=lambda *a, **kw: original.console.shell('bash')) as su:
            console.submit('$.su("other", password="fixture")')
        su.assert_called_once_with('other', password='fixture')
        self.assertEqual(len(console.layers), 3)
        console.submit('exit()')
        console.submit('$.exit()')
        self.assertIs(console.current, original)

    def test_stop_returns_to_console_but_script_exit_cannot_pop_it(self):
        console, _, _ = self.open_console()
        original = console.current
        console.submit('script = $.run("value=42\\n$.stop()\\nmissing=True")')
        self.assertTrue(console.namespace['script'].stopped)
        self.assertEqual(console.namespace['script']['value'], 42)
        self.assertIs(console.current, original)
        console.submit('$.run("$.exit()")')
        self.assertIsInstance(console.namespace['error'], AttributeError)
        self.assertIs(console.current, original)
        console.submit('exit()')
        self.assertTrue(console.done)

    def test_explicit_text_program_replies_and_exit_restore_shell(self):
        console, output, _ = self.open_console()
        original = console.current
        import shlex
        console.submit('$.enter(' + repr(shlex.quote(sys.executable) + ' -q -u') + ', prompt=">>>", exit="quit()")')
        self.assertEqual(console.current.kind, 'program')
        console.submit('print(6 * 7)')
        self.assertIn('42', output.getvalue())
        console.submit('exit()')
        self.assertIs(console.current, original)
        console.submit('$printf recovered')
        self.assertIn('recovered', output.getvalue())

    def test_keyboard_interrupt_stops_job_and_keeps_shell_usable(self):
        console, output, errors = self.open_console()
        import interactive
        console.submit('$.set(check=True)')
        real_sleep = interactive.time.sleep
        triggered = False
        caller_thread = threading.get_ident()
        def interrupt_once(seconds):
            nonlocal triggered
            if threading.get_ident() == caller_thread and not triggered:
                triggered = True
                real_sleep(0.2)
                raise KeyboardInterrupt
            real_sleep(seconds)
        with patch.object(interactive.time, 'sleep', side_effect=interrupt_once):
            console.submit('$sleep 30')
        self.assertIn('KeyboardInterrupt', errors.getvalue())
        self.assertIsNone(console.namespace['error'])
        console.submit('$printf after-interrupt')
        self.assertIn('after-interrupt', output.getvalue())

    def test_eof_closes_and_errors_do_not_echo_secrets(self):
        console, _, errors = self.open_console()
        entries = iter(['$.connect("host", password="private-fixture")'])
        def read(prompt):
            try:
                return next(entries)
            except StopIteration:
                raise EOFError
        console.input_func = read
        with patch.object(console.current.session, 'connect', side_effect=ValueError('private-fixture')):
            console.interact()
        self.assertTrue(console.done)
        self.assertNotIn('private-fixture', errors.getvalue())
        self.assertIn('operation failed', errors.getvalue())

    def test_help_keeps_current_environment(self):
        console, output, _ = self.open_console()
        original = console.current
        console.submit('help')
        console.submit('help()')
        self.assertEqual(output.getvalue().count('Input is Python'), 2)
        self.assertIs(console.current, original)
        self.assertFalse(console.done)
        with patch('interactive.builtins.help') as python_help:
            console.submit('help(str)')
        python_help.assert_called_once_with(str)

    def test_exit_helpers_leave_one_layer_and_unwind_python_finally(self):
        for statement in ('exit', 'exit()'):
            with self.subTest(statement=statement):
                console, _, errors = self.open_console()
                parent = console.current
                console.submit('value=42')
                console.submit('$.shell("bash")')
                if statement == 'exit':
                    console.submit('exit # leave one environment')
                else:
                    for line in ('try:', '    exit()', 'finally:', '    cleaned=True', ''):
                        console.submit(line)
                    self.assertTrue(console.namespace['cleaned'])
                self.assertIs(console.current, parent)
                self.assertFalse(console.done)
                self.assertEqual(console.namespace['value'], 42)
                console.submit(statement)
                self.assertTrue(console.done)
                self.assertTrue(parent.session.closed)
                self.assertEqual(errors.getvalue(), '')

    def test_program_layer_reserves_exit_and_quit_helpers(self):
        for statement in ('exit', 'exit()', 'quit', 'quit()'):
            with self.subTest(statement=statement):
                console, _, errors = self.open_console()
                parent = console.current
                self.enter_python(console)
                console.submit(statement)
                if statement.startswith('exit'):
                    self.assertIs(console.current, parent)
                    self.assertFalse(console.done)
                else:
                    self.assertTrue(console.done)
                    self.assertTrue(parent.session.closed)
                self.assertEqual(errors.getvalue(), '')

    def test_quit_helpers_close_all_layers_and_unwind_python_finally(self):
        for statement in ('quit', 'quit()'):
            with self.subTest(statement=statement):
                console, _, errors = self.open_console()
                session = console.current.session
                console.submit('$.shell("bash")')
                if statement == 'quit':
                    console.submit('quit # finish all environments')
                else:
                    for line in ('try:', '    '+statement, 'finally:', '    cleaned=True', ''):
                        console.submit(line)
                    self.assertTrue(console.namespace['cleaned'])
                self.assertTrue(console.done)
                self.assertTrue(session.closed)
                self.assertFalse(console.layers)
                self.assertEqual(errors.getvalue(), '')

    def test_script_exit_does_not_inherit_console_quit_helper(self):
        console, _, errors = self.open_console()
        console.submit('value=42')
        original = console.current
        for source in ('exit()', 'quit()', 'import sys; sys.exit()'):
            console.submit('$.run(' + repr(source) + ')')
            self.assertIs(console.current, original)
            self.assertFalse(console.done)
            self.assertEqual(console.namespace['value'], 42)
        self.assertEqual(errors.getvalue().count('console remains open'), 3)

    def test_helpers_can_be_shadowed_like_python_names(self):
        console, output, _ = self.open_console()
        console.submit('quit = "a variable"')
        console.submit('quit')
        self.assertIn('a variable', output.getvalue())
        self.assertFalse(console.done)
        console.submit('control.quit()')
        self.assertTrue(console.done)

    def test_ctrl_c_discards_multiline_input_and_preserves_namespace(self):
        console, output, errors = self.open_console()
        events = iter(['value=42', 'if True:', KeyboardInterrupt(), 'print(value)', EOFError()])
        def read(prompt):
            event = next(events)
            if isinstance(event, BaseException):
                raise event
            return event
        console.input_func = read
        console.interact()
        self.assertTrue(console.done)
        self.assertFalse(console.more)
        self.assertEqual(console.namespace['value'], 42)
        self.assertIn('42', output.getvalue())
        self.assertIn('KeyboardInterrupt', errors.getvalue())

    def test_python_execution_interrupt_keeps_console_and_variables(self):
        console, output, errors = self.open_console()
        console.submit('value=42')
        console.submit('raise KeyboardInterrupt')
        self.assertFalse(console.done)
        self.assertFalse(console.more)
        console.submit('print(value)')
        self.assertIn('42', output.getvalue())
        self.assertIn('KeyboardInterrupt', errors.getvalue())

    def test_error_commands_work_in_python_and_program_without_sending(self):
        console, output, errors = self.open_console()
        console.submit('raise TypeError("specific-fixture-detail")')
        self.assertNotIn('specific-fixture-detail', errors.getvalue())
        console.submit(':error')
        self.assertIn('TypeError: specific-fixture-detail', errors.getvalue())
        self.enter_python(console)
        channel = console.current.console.channel
        with patch.object(channel, 'send', wraps=channel.send) as send:
            console.submit(':error')
            console.submit(':traceback')
            console.submit(':status')
            send.assert_not_called()
        self.assertIn('Traceback (most recent call last)', errors.getvalue())
        self.assertIn('program:', output.getvalue())
        console.submit('$.exit()')
        console.submit('broken = )')
        console.submit(':error')
        self.assertIsInstance(console.namespace['error'], SyntaxError)
        self.assertIn('unmatched', errors.getvalue())

    def test_password_banner_and_exit_without_configured_prompt(self):
        import shlex
        import time
        console, output, errors = self.open_console()
        program = ("import time; input('Password: '); time.sleep(.15); "
                   "print('Welcome to the database', flush=True); "
                   "print('mysql> ', end='', flush=True); "
                   "reply=input(); time.sleep(.15); "
                   "print('Bye' if reply == 'quit' else 'unexpected reply', flush=True)")
        command = shlex.join([sys.executable, '-u', '-c', program])
        console.submit('$.enter(' + repr(command) + ')')
        self.assertIn('Password:', output.getvalue())
        update = console.send_input('fixture-password', timeout=.4)
        self.assertIn('Welcome to the database', output.getvalue())
        self.assertIn('mysql>', output.getvalue())
        self.assertEqual(update.error_type, 'TimeoutError')
        console.submit('$.exit("quit")')
        self.assertEqual(len(console.layers), 1)
        self.assertIn('Bye', output.getvalue())
        console.submit('$printf restored-shell')
        self.assertIn('restored-shell', output.getvalue())

    def test_detected_secret_uses_password_reader_then_restores_normal_input(self):
        import shlex
        console, output, errors = self.open_console()
        # This fixture disables its own PTY echo, as a real password reader does.
        program = ("import sys,time,termios; a=termios.tcgetattr(0); "
                   "a[3] &= ~termios.ECHO; termios.tcsetattr(0,termios.TCSANOW,a); "
                   "sys.stdout.write('\\x1b[33mEnter pass'); sys.stdout.flush(); "
                   "time.sleep(.05); value=input('word:\\x1b[0m '); "
                   "print('accepted' if value == '$.exit()' else 'wrong'); "
                   "a[3] |= termios.ECHO; termios.tcsetattr(0,termios.TCSANOW,a); "
                   "input('mysql> '); print('finished')")
        command = shlex.join([sys.executable, '-u', '-c', program])
        replies = iter(['select 1;', 'quit'])
        normal_calls = []
        def read(prompt):
            normal_calls.append(prompt)
            return next(replies)
        console.input_func = read
        with patch.object(console, 'password_func', return_value='$.exit()') as password:
            console.submit('$.enter(' + repr(command) + ')')
            self.assertTrue(console.current.secret_pending)
            console.interact()
        password.assert_called_once()
        self.assertEqual(len(normal_calls), 2)
        self.assertIn('accepted', output.getvalue())
        self.assertIn('finished', output.getvalue())
        self.assertNotIn('$.exit()', output.getvalue() + errors.getvalue())

    def test_manual_secret_input_is_literal_and_never_a_python_result(self):
        import shlex
        console, output, errors = self.open_console()
        program = ("import termios; a=termios.tcgetattr(0); a[3] &= ~termios.ECHO; "
                   "termios.tcsetattr(0,termios.TCSANOW,a); value=input('Custom challenge> '); "
                   "print('literal-ok' if value == '$.exit()' else 'wrong')")
        command = shlex.join([sys.executable, '-u', '-c', program])
        console.submit('$.enter(' + repr(command) + ')')
        self.assertFalse(console.current.secret_pending)
        with patch.object(console, 'password_func', return_value='$.exit()'):
            update = console.submit('$.input(secret=True)')
        self.assertEqual(len(console.layers), 1)
        self.assertIn('literal-ok', output.getvalue())
        self.assertNotIn('$.exit()', output.getvalue() + errors.getvalue() + update.stdout)
        self.assertIsNone(console.namespace['error'])

    def test_secret_reader_failure_or_cancel_sends_nothing(self):
        from interactive import CredentialsRequiredError
        console, _, _ = self.open_console()
        self.enter_python(console)
        channel = console.current.console.channel
        for error in (KeyboardInterrupt(), EOFError(), CredentialsRequiredError('unavailable')):
            with self.subTest(error=type(error).__name__), \
                 patch.object(console, 'password_func', side_effect=error), \
                 patch.object(channel, 'send', wraps=channel.send) as send:
                with self.assertRaises(type(error)):
                    console.input(secret=True)
                send.assert_not_called()
        with patch.object(console, 'password_func') as password:
            with self.assertRaises(ValueError):
                console.input('plaintext', secret=True)
            password.assert_not_called()
        console.submit('$.exit()')
        with patch.object(console, 'password_func') as password:
            with self.assertRaises(RuntimeError):
                console.input(secret=True)
            password.assert_not_called()

    def test_hidden_reader_refuses_getpass_echo_fallback(self):
        from getpass import GetPassWarning
        from interactive import CredentialsRequiredError
        def unsafe_getpass(prompt):
            warnings.warn('cannot control echo', GetPassWarning)
            self.fail('getpass must not reach its plaintext fallback')
        with patch('interactive.sys.stdin.isatty', return_value=True), \
             patch('interactive.getpass', side_effect=unsafe_getpass):
            with self.assertRaises(CredentialsRequiredError):
                Console._terminal_password()

    def test_terminal_secret_input_disables_and_restores_echo(self):
        import os
        import pty
        import select
        import signal
        import termios
        import time
        script = '''from interactive import Console
try:
    value = Console._terminal_password('Hidden fixture: ')
    print('ACCEPTED', len(value), flush=True)
except KeyboardInterrupt:
    print('CANCELLED', flush=True)
'''
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                master, slave = pty.openpty()
                process = None
                try:
                    before = termios.tcgetattr(slave)
                    process = subprocess.Popen([sys.executable, '-B', '-c', script],
                                               stdin=slave, stdout=slave, stderr=slave,
                                               start_new_session=True)
                    deadline = time.monotonic() + 10
                    result = bytearray()
                    while b'Hidden fixture: ' not in result:
                        self.assertIsNone(process.poll())
                        self.assertLess(time.monotonic(), deadline, repr(result))
                        if select.select([master], [], [], .05)[0]:
                            result.extend(os.read(master, 4096))
                    self.assertFalse(termios.tcgetattr(slave)[3] & termios.ECHO)
                    if cancel:
                        process.send_signal(signal.SIGINT)
                    else:
                        os.write(master, b'private-fixture\n')
                    process.wait(timeout=10)
                    self.assertEqual(process.returncode, 0)
                    self.assertEqual(termios.tcgetattr(slave), before)
                    while select.select([master], [], [], .1)[0]:
                        result.extend(os.read(master, 4096))
                    self.assertIn(b'CANCELLED' if cancel else b'ACCEPTED 15', result)
                    self.assertNotIn(b'private-fixture', result)
                finally:
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait()
                    os.close(master)
                    os.close(slave)

    def test_password_prompt_detection_uses_only_current_output_tail(self):
        from interactive import _Layer
        from unittest.mock import Mock
        from stdio import DequeString
        console = object.__new__(Console)
        console._stdout, console._stderr = io.StringIO(), io.StringIO()
        channel = Mock()
        channel._stdout, channel._stderr = DequeString(), DequeString()
        channel._interactive_layer_exited.return_value = False
        layer = _Layer(None, None, Mock(channel=channel), 'program', 'fixture', '?')
        console.layers = [layer]
        for part, expected in [('Enter pass', False), ('word: ', True),
                               ('\nmysql> ', False), ('\nPassword for alice: ', True),
                               ('\nprint("Password:")', False),
                               ('\nEnter passphrase for key "/key": ', True),
                               ('\n輸入密碼：', True), ('\nPassword: \nready> ', False)]:
            channel._stdout.append(part)
            console._drain_program()
            self.assertEqual(layer.secret_pending, expected, repr(part))

    def test_late_program_return_does_not_send_another_exit_to_parent(self):
        import shlex
        import time
        console, output, errors = self.open_console()
        command = shlex.join([sys.executable, '-u', '-c',
                              "input('ready> '); import time; time.sleep(.4)"])
        console.submit('$.enter(' + repr(command) + ', prompt="ready> ")')
        console.send_input('quit', timeout=.1)
        channel = console.current.console.channel
        parent_prompt = channel.prompts[-2]
        deadline = time.monotonic() + 10
        while not any(parent_prompt in str(buffer)
                      for buffer in (channel._stdout, channel._stderr)):
            self.assertLess(time.monotonic(), deadline,
                            'fixture did not return to its parent shell')
            time.sleep(.01)
        with patch.object(channel, 'send', wraps=channel.send) as send:
            console.submit('$.exit("quit")')
        self.assertNotIn('quit\n', [call.args[0] for call in send.call_args_list])
        self.assertEqual(len(console.layers), 1)
        console.submit('$printf parent-still-alive')
        self.assertIn('parent-still-alive', output.getvalue())

    def test_cli_uses_new_connection_flags_and_rejects_removed_spellings(self):
        from interactive import main
        with patch('interactive.Console') as cls, patch('interactive.Session'):
            main(['fixture', '--parent-key-filename', '/fixture/key',
                  '--known-hosts-source', 'chain', '--proxy-command', 'fixture-command'])
            cls.return_value.__enter__.return_value.connect.assert_called_once_with(
                'fixture', parent_key_filename='/fixture/key', known_hosts_source='chain',
                proxy_command='fixture-command')
        for flag in ('--pkey-path', '--known-hosts'):
            with self.subTest(flag=flag), patch('interactive.Session') as create, \
                 patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit):
                    main(['fixture', flag, 'value'])
                create.assert_not_called()

    def enter_python(self, console):
        import shlex
        console.submit('$.enter(' + repr(shlex.quote(sys.executable) + ' -q -u') + ', prompt=">>>", exit="quit()")')
        self.assertEqual(console.current.kind, 'program')

    def test_exit_without_program_command_warns_without_sending(self):
        console, output, errors = self.open_console()
        import shlex
        console.submit('$.enter(' + repr(shlex.quote(sys.executable) + ' -q -u') + ', prompt=">>>")')
        program = console.current
        with patch.object(program.console.channel, 'send', wraps=program.console.channel.send) as send:
            for source in ('$.exit()', 'exit', 'exit()'):
                console.submit(source)
                self.assertIs(console.current, program)
            send.assert_not_called()
        self.assertEqual(errors.getvalue().count('Program remains open'), 3)
        self.assertEqual(console._state, 'running')
        console.submit('$.exit("quit()")')
        self.assertEqual(len(console.layers), 1)
        self.assertEqual(console.namespace['result'].exitcode, 0)
        console.submit('$printf recovered')
        self.assertIn('recovered', output.getvalue())

    def test_exit_command_must_really_exit_and_can_override_default(self):
        console, output, errors = self.open_console()
        self.enter_python(console)
        program = console.current
        console.submit('$.exit("print(42)")')
        self.assertIs(console.current, program)
        self.assertIn('42', output.getvalue())
        self.assertIn('current layer remains open', errors.getvalue())
        console.submit('$.exit()')
        self.assertEqual(len(console.layers), 1)

    def test_dollar_exit_unwinds_finally_and_leaves_only_one_layer(self):
        console, _, errors = self.open_console()
        parent = console.current
        console.submit('$.shell("bash")')
        for line in ('try:', '    $.exit()', 'finally:', '    cleaned=True', ''):
            console.submit(line)
        self.assertTrue(console.namespace['cleaned'])
        self.assertIs(console.current, parent)
        console.submit('$.exit("quit")')
        self.assertIs(console.current, parent)
        self.assertIsInstance(console.namespace['error'], ValueError)
        console.submit('$.exit()')
        self.assertTrue(console.done)

    def test_ctrl_c_and_ctrl_d_go_to_program_and_restore_python_parent(self):
        console, output, errors = self.open_console()
        original = console.current
        console.submit('value=42')
        self.enter_python(console)
        program = console.current
        events = iter([KeyboardInterrupt(), 'print(6*7)', EOFError(), 'print(value)', 'quit'])
        prompts = []
        def read(prompt):
            prompts.append(prompt)
            event = next(events)
            if isinstance(event, BaseException):
                raise event
            return event
        console.input_func = read
        channel = program.console.channel
        parent_prompt = channel.prompts[-2]
        with patch.object(channel, 'send', wraps=channel.send) as send:
            console.interact()
        payloads = [call.args[0] for call in send.call_args_list]
        self.assertIn('\x03', payloads)
        self.assertIn('\x04', payloads)
        self.assertNotIn('\x03\n', payloads)
        self.assertNotIn('\x04\n', payloads)
        self.assertTrue(console.done)
        self.assertTrue(original.session.closed)
        self.assertEqual(console.namespace['value'], 42)
        self.assertGreaterEqual(output.getvalue().count('42'), 2)
        self.assertNotIn('program>', prompts[-1])
        self.assertNotIn(parent_prompt, output.getvalue())
        self.assertEqual(errors.getvalue(), '')

    def test_interrupt_during_program_execution_reaches_program(self):
        console, output, errors = self.open_console()
        original = console.current
        self.enter_python(console)
        channel = console.current.console.channel
        wait = channel._wait_input_completion
        interrupted = False
        def interrupt_once(*args, **kwargs):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                import time
                time.sleep(0.2)
                raise KeyboardInterrupt
            return wait(*args, **kwargs)
        with patch.object(channel, '_wait_input_completion', side_effect=interrupt_once):
            console.submit('import time; time.sleep(30)')
        self.assertEqual(console.current.kind, 'program')
        console.submit('print(6*7)')
        self.assertIn('42', output.getvalue())
        console.eof()
        self.assertIs(console.current, original)
        self.assertFalse(console.done)
        self.assertEqual(errors.getvalue(), '')

    def test_terminal_backspace_edits_input_with_either_erase_code(self):
        import errno
        import os
        import pty
        import select
        import termios
        import time
        try:
            import readline
        except ImportError:
            self.skipTest('Python has no readline support')
        root = Path(__file__).resolve().parents[1]
        for erase, backspace in ((b'\x08', b'\x7f'), (b'\x7f', b'\x08')):
            with self.subTest(erase=erase, backspace=backspace):
                master, slave = pty.openpty()
                process = None
                try:
                    attributes = termios.tcgetattr(slave)
                    attributes[6][termios.VERASE] = erase
                    termios.tcsetattr(slave, termios.TCSANOW, attributes)
                    process = subprocess.Popen(
                        [sys.executable, '-B', str(root / 'sshscript.py'), 'console'],
                        stdin=slave, stdout=slave, stderr=slave,
                        env={**os.environ, 'TERM': 'xterm'})
                    os.close(slave)
                    slave = None
                    def read_until(marker):
                        output = b''
                        deadline = time.monotonic() + 20
                        while marker is None or marker not in output:
                            if time.monotonic() >= deadline:
                                self.fail(f'terminal timed out: {output!r}')
                            if select.select([master], [], [], 0.1)[0]:
                                try:
                                    chunk = os.read(master, 65536)
                                except OSError as error:
                                    if error.errno == errno.EIO:
                                        break
                                    raise
                                if not chunk:
                                    break
                                output += chunk
                        # libedit may flush pending input while switching to
                        # editing mode immediately after writing its prompt.
                        time.sleep(0.05)
                        return output
                    read_until(b'> ')
                    os.write(master, b'value=12' + backspace + b'3\n')
                    edited = read_until(b'> ')
                    self.assertNotIn(b'SyntaxError', edited)
                    os.write(master, b'print("EDITED", value)\n')
                    self.assertIn(b'EDITED 13', read_until(b'> '))
                    os.write(master, b'quit\n' if backspace == b'\x7f' else b'\x04')
                    # Drain terminal output while closing; macOS can wait for
                    # the PTY output to drain before restoring terminal modes.
                    read_until(None)
                    process.wait(timeout=15)
                    self.assertEqual(process.returncode, 0)
                finally:
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait()
                    os.close(master)
                    if slave is not None:
                        os.close(slave)

    def test_cli_accepts_repeated_input_without_script_file(self):
        root = Path(__file__).resolve().parents[1]
        cli = subprocess.run([sys.executable, str(root / 'sshscript.py'), 'console'],
                             input='value=40\n$printf ready\nprint(value+2)\nprint($.stdout)\nexit\n',
                             text=True, capture_output=True, timeout=30)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn('ready', cli.stdout)
        self.assertIn('42', cli.stdout)
        self.assert_no_unexpected_stderr(cli.stderr)


if __name__ == '__main__':
    unittest.main()
