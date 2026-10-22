"""Public regressions for retained console state and script completion boundaries."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
from unittest.mock import patch

import sshscript
import patching
from interactive import InteractiveConsole
from scriptcontrol import ScriptResult
from session import Session


class ScriptControlTests(unittest.TestCase):
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
            self.assertEqual(cli.stderr, '')

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


class InteractiveTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(warnings.catch_warnings())
        warnings.filterwarnings('ignore', message="'get_child_watcher' is deprecated.*",
                                category=DeprecationWarning, module=r'asyncio\.events')

    def open_console(self):
        output, errors = io.StringIO(), io.StringIO()
        console = InteractiveConsole(stdout=output, stderr=errors).open()
        self.addCleanup(console.close)
        return console, output, errors

    def test_directory_environment_variables_python_and_failure_survive_inputs(self):
        console, output, errors = self.open_console()
        with tempfile.TemporaryDirectory() as folder:
            import shlex
            console.execute('$cd ' + shlex.quote(folder))
            console.execute('$export CONSOLE_FIXTURE=retained')
            console.execute('$pwd; printf "%s" "$CONSOLE_FIXTURE"')
            self.assertIn(folder, output.getvalue())
            self.assertIn('retained', output.getvalue())
            console.execute('$false')
            self.assertEqual(console.namespace['result'].exitcode, 1)
            self.assertIn('[exit 1]', errors.getvalue())
            console.execute('options = {"port": 2222}')
            console.execute('for index in range(2):')
            console.execute('    options["count"] = index')
            console.execute('')
            console.execute('$printf after-failure')
            self.assertIn('after-failure', output.getvalue())
            self.assertEqual(console.namespace['options'], {'port': 2222, 'count': 1})
            console.execute('print(options["port"])')
            self.assertIn('2222', output.getvalue())

    def test_bare_name_is_python_and_never_an_implicit_shell_command(self):
        console, output, errors = self.open_console()
        with patch.object(console, 'exec_command') as execute:
            console.execute('hostname')
            self.assertIn('NameError', errors.getvalue())
            console.execute('hostname = "a Python variable"')
            console.execute('hostname')
            execute.assert_not_called()
        self.assertIn('a Python variable', output.getvalue())

    def test_dollar_command_result_is_available_inside_python_expressions(self):
        console, output, errors = self.open_console()
        console.execute('$printf host-fixture')
        self.assertEqual(output.getvalue(), 'host-fixture')
        console.execute('print($.stdout)')
        console.execute('hostname = $.stdout.strip()')
        console.execute('status = $.exitcode')
        self.assertEqual(console.namespace['hostname'], 'host-fixture')
        self.assertEqual(console.namespace['status'], 0)
        console.execute('message = f"host={$.stdout.strip()}"')
        self.assertEqual(console.namespace['message'], 'host=host-fixture')
        console.execute('out, err, status = $printf another-host')
        self.assertEqual((console.namespace['out'], console.namespace['err'], console.namespace['status']),
                         ('another-host', '', 0))
        console.execute('literal = "$.stdout is text, not evaluation"')
        self.assertEqual(console.namespace['literal'], '$.stdout is text, not evaluation')
        self.assertEqual(errors.getvalue(), '')

    def test_dollar_commands_in_python_multiline_loop_and_function(self):
        console, output, errors = self.open_console()
        for line in ['for index in range(2):', '    $f"echo item-{index}"', '']:
            console.execute(line)
        self.assertIn('item-0', output.getvalue())
        self.assertIn('item-1', output.getvalue())
        for line in ['def read_host():', '    $printf function-host', '    return $.stdout', '']:
            console.execute(line)
        console.execute('saved = read_host()')
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
            console.execute('$.connect(')
            self.assertTrue(console.more)
            connect.assert_not_called()
            console.execute('    host,')
            self.assertTrue(console.more)
            console.execute('    username="ops",')
            console.execute(')')
        connect.assert_called_once_with('fixture', username='ops')
        self.assertFalse(console.more)
        self.assertEqual(len(console.layers), 2)
        console.execute('exit()')
        self.assertEqual(errors.getvalue(), '')

    def test_syntax_error_recovers_for_next_input(self):
        console, _, errors = self.open_console()
        console.execute('$.stdout + )')
        self.assertFalse(console.more)
        self.assertIn('SyntaxError', errors.getvalue())
        console.execute('value = 42')
        self.assertEqual(console.namespace['value'], 42)

    def test_lexical_with_uses_normal_spy_scope_and_restores_stack(self):
        console, output, errors = self.open_console()
        original = console.current
        stack = patching.get_thread_stack().snapshot()
        for line in ['with $.shell("bash"):', '    $printf lexical-host', '    saved = str($.stdout)', '']:
            console.execute(line)
        self.assertEqual(console.namespace['saved'], 'lexical-host')
        self.assertIs(console.current, original)
        self.assertEqual(patching.get_thread_stack().snapshot(), stack)
        self.assertEqual(errors.getvalue(), '')

    def test_program_exit_returns_to_python_console_without_extra_exit(self):
        console, output, errors = self.open_console()
        original = console.current
        import shlex
        console.execute('$.enter(' + repr(shlex.quote(sys.executable) + ' -q -u') + ', prompt=">>>", exit="quit()")')
        console.execute('raise SystemExit')
        self.assertIs(console.current, original)
        console.execute('value = 42')
        self.assertEqual(console.namespace['value'], 42)
        self.assertEqual(errors.getvalue(), '')

    def test_nested_shell_exit_restores_parent_and_root_exit_closes(self):
        console, output, errors = self.open_console()
        original = console.current
        original_stack = patching.get_thread_stack().snapshot()
        console.execute('$.shell("bash")')
        self.assertEqual(len(console.layers), 2)
        console.execute('exit()')
        self.assertIs(console.current, original)
        self.assertEqual(patching.get_thread_stack().snapshot(), original_stack)
        console.execute('$printf parent-restored')
        self.assertIn('parent-restored', output.getvalue())
        console.execute('exit()')
        self.assertTrue(console.done)
        self.assertTrue(original.session.closed)
        console.close()

    def test_dollar_session_and_wrapper_exit_are_removed_in_console(self):
        console, _, _ = self.open_console()
        console.execute('$.shell("bash")')
        current = console.current
        for source in ('$.exit()', 'session.exit()', 'console.exit()'):
            console.execute(source)
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
            console.execute('$.connect(host, password="literal", **options)')
        connect.assert_called_once_with('fixture', password='literal', username='ops', port=2222)
        self.assertEqual(len(console.layers), 2)
        console.execute('exit()')
        self.assertIs(console.current, parent)
        self.assertTrue(remote.closed)
        self.assertFalse(parent.session.closed)

    def test_failed_connection_shell_entry_rolls_back(self):
        console, _, _ = self.open_console()
        parent = console.current
        remote = Session()
        with patch.object(parent.session, 'connect', return_value=remote), \
             patch.object(remote, 'shell', side_effect=RuntimeError('fixture shell failure')):
            console.execute('$.connect("fixture")')
            self.assertIsInstance(console.namespace['error'], RuntimeError)
        self.assertTrue(remote.closed)
        self.assertIs(console.current, parent)
        console.execute('$true')

    def test_identity_layers_route_parameters_and_unwind(self):
        # Use real shell layers as credential-free stand-ins for auth; native
        # su/sudo handshakes remain covered by the dedicated native matrix.
        console, _, _ = self.open_console()
        original = console.current
        with patch.object(original.console, 'sudo', side_effect=lambda **kw: original.console.shell('bash')) as sudo:
            console.execute('$.sudo(password=None, username="fixture")')
        sudo.assert_called_once_with(password=None, username='fixture')
        self.assertEqual(console.current.kind, 'sudo')
        console.execute('$.connect("other")')
        self.assertIsInstance(console.namespace['error'], RuntimeError)
        self.assertIn('credentials', str(console.namespace['error']))
        with patch.object(console.current.console, 'su', side_effect=lambda *a, **kw: original.console.shell('bash')) as su:
            console.execute('$.su("other", password="fixture")')
        su.assert_called_once_with('other', password='fixture')
        self.assertEqual(len(console.layers), 3)
        console.execute('exit()')
        console.execute('exit()')
        self.assertIs(console.current, original)

    def test_stop_returns_to_console_but_script_exit_cannot_pop_it(self):
        console, _, _ = self.open_console()
        original = console.current
        console.execute('script = $.run("value=42\\n$.stop()\\nmissing=True")')
        self.assertTrue(console.namespace['script'].stopped)
        self.assertEqual(console.namespace['script']['value'], 42)
        self.assertIs(console.current, original)
        console.execute('$.run("$.exit()")')
        self.assertIsInstance(console.namespace['error'], AttributeError)
        self.assertIs(console.current, original)
        console.execute('exit()')
        self.assertTrue(console.done)

    def test_explicit_text_program_replies_and_exit_restore_shell(self):
        console, output, _ = self.open_console()
        original = console.current
        import shlex
        console.execute('$.enter(' + repr(shlex.quote(sys.executable) + ' -q -u') + ', prompt=">>>", exit="quit()")')
        self.assertEqual(console.current.kind, 'program')
        console.execute('print(6 * 7)')
        self.assertIn('42', output.getvalue())
        console.execute('exit()')
        self.assertIs(console.current, original)
        console.execute('$printf recovered')
        self.assertIn('recovered', output.getvalue())

    def test_keyboard_interrupt_stops_job_and_keeps_shell_usable(self):
        console, output, errors = self.open_console()
        import interactive
        console.execute('$.set(check=True)')
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
            console.execute('$sleep 30')
        self.assertIn('KeyboardInterrupt', errors.getvalue())
        self.assertIsNone(console.namespace['error'])
        console.execute('$printf after-interrupt')
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
        console.execute('help')
        console.execute('help()')
        self.assertEqual(output.getvalue().count('Input is Python'), 2)
        self.assertIs(console.current, original)
        self.assertFalse(console.done)
        with patch('interactive.builtins.help') as python_help:
            console.execute('help(str)')
        python_help.assert_called_once_with(str)

    def test_exit_helpers_leave_one_layer_and_unwind_python_finally(self):
        for statement in ('exit', 'exit()'):
            with self.subTest(statement=statement):
                console, _, errors = self.open_console()
                parent = console.current
                console.execute('value=42')
                console.execute('$.shell("bash")')
                if statement == 'exit':
                    console.execute('exit # leave one environment')
                else:
                    for line in ('try:', '    exit()', 'finally:', '    cleaned=True', ''):
                        console.execute(line)
                    self.assertTrue(console.namespace['cleaned'])
                self.assertIs(console.current, parent)
                self.assertFalse(console.done)
                self.assertEqual(console.namespace['value'], 42)
                console.execute(statement)
                self.assertTrue(console.done)
                self.assertTrue(parent.session.closed)
                self.assertEqual(errors.getvalue(), '')

    def test_program_layer_reserves_exit_and_quit_helpers(self):
        for statement in ('exit', 'exit()', 'quit', 'quit()'):
            with self.subTest(statement=statement):
                console, _, errors = self.open_console()
                parent = console.current
                self.enter_python(console)
                console.execute(statement)
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
                console.execute('$.shell("bash")')
                if statement == 'quit':
                    console.execute('quit # finish all environments')
                else:
                    for line in ('try:', '    '+statement, 'finally:', '    cleaned=True', ''):
                        console.execute(line)
                    self.assertTrue(console.namespace['cleaned'])
                self.assertTrue(console.done)
                self.assertTrue(session.closed)
                self.assertFalse(console.layers)
                self.assertEqual(errors.getvalue(), '')

    def test_script_exit_does_not_inherit_console_quit_helper(self):
        console, _, errors = self.open_console()
        console.execute('value=42')
        original = console.current
        for source in ('exit()', 'quit()', 'import sys; sys.exit()'):
            console.execute('$.run(' + repr(source) + ')')
            self.assertIs(console.current, original)
            self.assertFalse(console.done)
            self.assertEqual(console.namespace['value'], 42)
        self.assertEqual(errors.getvalue().count('console remains open'), 3)

    def test_helpers_can_be_shadowed_like_python_names(self):
        console, output, _ = self.open_console()
        console.execute('quit = "a variable"')
        console.execute('quit')
        self.assertIn('a variable', output.getvalue())
        self.assertFalse(console.done)
        console.execute('control.quit()')
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
        console.execute('value=42')
        console.execute('raise KeyboardInterrupt')
        self.assertFalse(console.done)
        self.assertFalse(console.more)
        console.execute('print(value)')
        self.assertIn('42', output.getvalue())
        self.assertIn('KeyboardInterrupt', errors.getvalue())

    def enter_python(self, console):
        import shlex
        console.execute('$.enter(' + repr(shlex.quote(sys.executable) + ' -q -u') + ', prompt=">>>", exit="quit()")')
        self.assertEqual(console.current.kind, 'program')

    def test_ctrl_c_and_ctrl_d_go_to_program_and_restore_python_parent(self):
        console, output, errors = self.open_console()
        original = console.current
        console.execute('value=42')
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
            console.execute('import time; time.sleep(30)')
        self.assertEqual(console.current.kind, 'program')
        console.execute('print(6*7)')
        self.assertIn('42', output.getvalue())
        console._eof()
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
        self.assertEqual(cli.stderr, '')


if __name__ == '__main__':
    unittest.main()
