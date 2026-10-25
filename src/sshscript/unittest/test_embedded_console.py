"""Local-process evidence and explicitly mocked identity/transport failures."""
import contextlib
import io
import shlex
import sys
import subprocess
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from sshscript import (Console, Session, CredentialsRequiredError,
                       ConsoleCleanupError, ConsoleInitializationError,
                       SwitchCredentials)


class EmbeddedConsoleTests(unittest.TestCase):
    def session(self):
        session = Session()
        self.addCleanup(session.close)
        return session

    def console(self, session=None, **kwargs):
        console = Console(session or self.session(), **kwargs)
        self.addCleanup(console.close)
        return console

    def complete(self, console, update):
        outputs = [update.stdout]
        deadline = time.monotonic() + 8
        while update.state == 'running':
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.02)
            update = console.poll()
            outputs.append(update.stdout)
        return update, ''.join(outputs)

    def test_borrow_without_auth_settings_mutation_and_reuse(self):
        session = self.session()
        session.set(verbose=True)
        settings = session.get()
        with patch.object(session, 'connect', side_effect=AssertionError('must not reconnect')):
            console = self.console(session)
            self.assertIs(console.connection, session)
            self.assertEqual(session.get(), settings)
            console.close()
        self.assertEqual(console.session_reuse, 'confirmed')
        self.assertFalse(session.closed)
        self.assertEqual(session('printf alive').stdout, 'alive')

    def test_python_shell_state_and_result_failures(self):
        console = self.console()
        self.assertEqual(console.submit('values = []').state, 'completed')
        self.assertEqual(console.submit('for n in range(2):').state, 'incomplete')
        self.assertEqual(console.submit('    values.append(n)').state, 'incomplete')
        self.assertEqual(console.submit('').state, 'completed')
        self.assertEqual(console.namespace['values'], [0, 1])
        console.submit('$cd /tmp; export EMBEDDED_TEST=preserved')
        update, output = self.complete(console, console.start_command('pwd; printf "$EMBEDDED_TEST"'))
        self.assertEqual(update.state, 'completed')
        self.assertIn('preserved', output)
        self.assertIn('tmp', output)
        update = console.submit('$false')
        self.assertEqual((update.state, update.result.exitcode), ('failed', 1))
        self.assertEqual(console.submit('bad = )').state, 'failed')
        self.assertEqual(console.submit('1/0').error_type, 'ZeroDivisionError')
        self.assertEqual(console.submit('assert values == [0, 1]').state, 'completed')

    def test_no_credentials_in_repr_or_diagnostics(self):
        console = self.console()
        self.assertNotIn('secret-value', repr(SwitchCredentials('secret-value')))
        for source in ('raise ValueError("secret-value")',
                       'raise SystemExit("secret-value")',
                       'password="secret-value"; broken=)'):
            update = console.submit(source)
            self.assertEqual(update.state, 'failed')
            self.assertNotIn('secret-value', update.stdout + update.stderr)

    def test_missing_credentials_is_structured_and_never_prompts(self):
        console = self.console(password_func=lambda _: self.fail('hidden password prompt'))
        update = console.submit('$.su("nobody")')
        self.assertEqual(update.error_type, 'CredentialsRequiredError')
        with self.assertRaises(CredentialsRequiredError):
            console.sudo()
        self.assertEqual(len(console.environments), 1)
        default_console = self.console()
        self.assertEqual(default_console.submit('getpass()').error_type, 'CredentialsRequiredError')

    def test_policy_and_credentials_hooks_with_simulated_identity(self):
        outcomes, requests = [], []
        def resolve(request):
            requests.append(request)
            return SwitchCredentials('private-password')
        console = self.console(credential_resolver=resolve, switch_observer=outcomes.append)
        # Shell contexts simulate identity nesting only; this is not native su.
        def simulated_switch(kind, *args, **kwargs):
            self.assertEqual(kwargs['password'], 'private-password')
            Console._console_layer(console, 'shell', 'bash')
            console.current.kind, console.current.user = kind, 'simulated-root'
        with patch.object(console, '_console_layer', side_effect=simulated_switch):
            console.su('target', password='ignored')
        self.assertEqual(console.environments[-1].effective_user, 'simulated-root')
        self.assertEqual(console.environments[-1].kind, 'su')
        self.assertTrue(requests[0].credential_supplied)
        self.assertNotIn('private-password', repr(requests) + repr(outcomes))
        self.assertTrue(outcomes[0].success)
        console.leave()
        self.assertEqual(len(console.environments), 1)

    def test_policy_rejection_and_auth_failure_notify_without_secrets(self):
        outcomes = []
        console = self.console(credential_resolver=lambda _: (_ for _ in ()).throw(PermissionError('secret')),
                               switch_observer=outcomes.append)
        update = console.submit('$.sudo(password=None)')
        self.assertEqual(update.error_type, 'PermissionError')
        self.assertFalse(outcomes[-1].success)
        self.assertNotIn('secret', repr(outcomes) + update.stderr)
        console._resolver = lambda _: SwitchCredentials(None)
        with patch.object(console, '_console_layer', side_effect=PermissionError('secret')):
            update = console.submit('$.su("target")')
        self.assertFalse(outcomes[-1].success)
        self.assertEqual(update.state, 'failed')

    def test_owned_session_and_host_exception(self):
        session = self.session()
        with self.assertRaisesRegex(ValueError, 'host failure'):
            with Console(session, ownership='owned'):
                raise ValueError('host failure')
        self.assertTrue(session.closed)
        borrowed = self.session()
        with self.assertRaises(ValueError):
            with Console(borrowed):
                raise ValueError('host failure')
        self.assertFalse(borrowed.closed)
        self.assertEqual(borrowed('printf alive').stdout, 'alive')

    def test_initialization_failure_preserves_borrowed_closes_owned(self):
        for ownership in ('borrowed', 'owned'):
            session = self.session()
            # Failure after channel acquisition exercises the real context unwind.
            with patch.object(Console, '_push', side_effect=RuntimeError('secret')):
                with self.assertRaises(ConsoleInitializationError) as caught:
                    Console(session, ownership=ownership)
            self.assertEqual(caught.exception.session_reuse, 'unknown')
            self.assertNotIn('secret', str(caught.exception))
            self.assertEqual(session.closed, ownership == 'owned')
            if ownership == 'borrowed':
                self.assertEqual(session('printf alive').stdout, 'alive')

    def test_cleanup_failure_and_repeated_close_are_explicit(self):
        session = self.session()
        console = Console(session)
        console.layers[-1].resources.callback(lambda: (_ for _ in ()).throw(RuntimeError('secret')))
        for _ in range(2):
            with self.assertRaises(ConsoleCleanupError) as caught:
                console.close()
            self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(console.session_reuse, 'unknown')
        self.assertFalse(session.closed)

    def test_failed_health_probe_reports_unknown(self):
        session = self.session()
        console = Console(session)
        with patch.object(session, 'exec_command', side_effect=ConnectionError('private server text')):
            with self.assertRaises(ConsoleCleanupError):
                console.close()
        self.assertEqual(console.session_reuse, 'unknown')

    def test_poll_interrupt_timeout_and_exclusivity(self):
        console = self.console()
        update = console.start_command('sleep 30', timeout=5, stop_timeout=1)
        self.assertEqual(update.state, 'running')
        with self.assertRaises(RuntimeError):
            console.submit('value=1')
        update = console.interrupt()
        self.assertEqual(update.state, 'failed')
        self.assertEqual(update.result.stop_reason, 'cancelled')
        self.assertEqual(update.result.termination_status, 'confirmed')
        update, _ = self.complete(console, console.start_command('sleep 30', timeout=.15, stop_timeout=1))
        self.assertEqual((update.state, update.error_type), ('failed', 'CommandTimeoutError'))
        self.assertEqual(console.submit('$printf recovered').stdout, 'recovered')

    def test_input_program_state_and_layers(self):
        console = self.console()
        command = shlex.quote(sys.executable) + ' -q -u'
        console.enter(command, prompt='>>>', exit='quit()')
        self.assertFalse(console.environments[-1].identity_verified)
        update = console.send_input('print("program-value")', timeout=2)
        self.assertEqual(update.state, 'waiting_input')
        self.assertIn('program-value', update.stdout)
        update = console.send_input('raise SystemExit', timeout=2)
        self.assertEqual(update.state, 'completed')
        self.assertEqual(len(console.environments), 1)

    def test_program_idle_interrupt_retains_readiness_and_cleanup(self):
        # Real Python and PTY; no host TTY or simulated prompt outcomes.
        for ending in ('eof', 'leave', 'close'):
            with self.subTest(ending=ending):
                session = self.session()
                console = self.console(session)
                console.enter(shlex.quote(sys.executable) + ' -q -u',
                              prompt='>>>', exit='quit()')
                self.assertEqual(console.poll().state, 'waiting_input')
                update = console.interrupt()
                self.assertEqual(update.state, 'waiting_input')
                self.assertEqual(update.error_type, 'KeyboardInterrupt')
                # The protocol consumed the prompt; polls must retain readiness
                # without sending extra input to provoke another prompt.
                for _ in range(3):
                    self.assertEqual(console.poll().state, 'waiting_input')
                update = console.send_input('print(6 * 7)', timeout=2)
                self.assertEqual(update.state, 'waiting_input')
                self.assertIn('42', update.stdout)
                getattr(console, ending)()
                if ending != 'close':
                    self.assertEqual(len(console.environments), 1)
                    self.assertFalse(console.done)
                self.assertEqual(console.close().session_reuse, 'confirmed')
                self.assertFalse(session.closed)
                self.assertEqual(session('printf owner-alive').stdout, 'owner-alive')

    def test_exit_retains_final_output_in_submit_update_without_prompt(self):
        console = self.console()
        command = shlex.join([sys.executable, '-u', '-c',
                              "input('ready> '); print('final-output', flush=True)"])
        console.enter(command)
        update = console.submit('$.exit("quit")')
        self.assertIn('final-output', update.stdout)
        self.assertEqual(len(console.environments), 1)
        self.assertEqual(update.result.exitcode, 0)

    def test_running_program_interrupt_recovers_prompt(self):
        console = self.console()
        console.enter(shlex.quote(sys.executable) + ' -q -u',
                      prompt='>>>', exit='quit()')
        update = console.send_input('import time; print("sleep-started", flush=True); time.sleep(30)',
                                    timeout=.3)
        self.assertEqual(update.state, 'running')
        self.assertIn('sleep-started\n', (update.stdout + console.poll().stdout).replace('\r\n', '\n'))
        update = console.interrupt()
        self.assertEqual(update.state, 'waiting_input')
        self.assertEqual(console.poll().state, 'waiting_input')
        self.assertEqual(console.send_input('print("recovered")').state, 'waiting_input')
        console.eof()
        self.assertEqual(console.close().session_reuse, 'confirmed')

    def test_program_ignoring_interrupt_stays_running_until_real_prompt(self):
        console = self.console()
        console.enter(shlex.quote(sys.executable) + ' -q -u',
                      prompt='>>>', exit='quit()')
        console.send_input('import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN)')
        update = console.send_input('print("ignoring-started", flush=True); time.sleep(4)', timeout=.3)
        self.assertEqual(update.state, 'running')
        self.assertIn('ignoring-started\n', (update.stdout + console.poll().stdout).replace('\r\n', '\n'))
        update = console.interrupt()
        self.assertEqual(update.state, 'running')
        self.assertEqual(console.poll().state, 'running')
        update, _ = self.complete(console, update)
        self.assertEqual(update.state, 'waiting_input')
        self.assertEqual(console.send_input('print("still-alive")').state, 'waiting_input')
        console.leave()
        self.assertEqual(console.close().session_reuse, 'confirmed')

    def test_program_interrupt_delayed_prompt_recovers_via_poll(self):
        console = self.console()
        console.enter(shlex.quote(sys.executable) + ' -q -u',
                      prompt='>>>', exit='quit()')
        source = 'import time\ntry:\n print("delay-started", flush=True); time.sleep(30)\nexcept KeyboardInterrupt:\n time.sleep(3)'
        update = console.send_input('exec(' + repr(source) + ')', timeout=.3)
        self.assertEqual(update.state, 'running')
        self.assertIn('delay-started\n', (update.stdout + console.poll().stdout).replace('\r\n', '\n'))
        update = console.interrupt()
        self.assertEqual(update.state, 'running')
        update, _ = self.complete(console, update)
        self.assertEqual(update.state, 'waiting_input')
        self.assertEqual(console.poll().state, 'waiting_input')
        console.eof()
        self.assertEqual(console.close().session_reuse, 'confirmed')

    def test_program_exit_on_interrupt_preserves_real_status(self):
        session = self.session()
        console = self.console(session)
        console.enter(shlex.quote(sys.executable) + ' -q -u',
                      prompt='>>>', exit='quit()')
        console.send_input('import signal; signal.signal(signal.SIGINT, signal.SIG_DFL)')
        update = console.interrupt()
        self.assertEqual(update.state, 'failed')
        self.assertEqual(update.result.exitcode, 130)
        self.assertEqual(len(console.environments), 1)
        self.assertEqual(console.close().session_reuse, 'confirmed')
        self.assertEqual(session('printf restored').stdout, 'restored')

    def test_quit_eof_leave_and_keyboard_interrupt(self):
        for action in ('quit', 'eof', 'leave'):
            session = self.session()
            console = Console(session)
            console.shell('bash')
            console.leave()
            if action == 'quit':
                update = console.submit('quit')
                self.assertEqual(update.state, 'closed')
            else:
                getattr(console, action)()
            self.assertEqual(console.session_reuse, 'confirmed')
            self.assertFalse(session.closed)
        console = self.console()
        console.submit('for n in range(2):')
        self.assertEqual(console.interrupt().state, 'ready')
        self.assertEqual(console.submit('x=42').state, 'completed')


    def test_program_failure_has_real_exit_status(self):
        console = self.console()
        console.enter(shlex.quote(sys.executable) + ' -q -u', prompt='>>>', exit='quit()')
        update = console.send_input('raise SystemExit(7)', timeout=2)
        self.assertEqual(update.state, 'failed')
        self.assertEqual(update.result.exitcode, 7)

    def test_program_timeout_then_poll_recovers_completion(self):
        console = self.console()
        console.enter(shlex.quote(sys.executable) + ' -q -u', prompt='>>>', exit='quit()')
        update = console.send_input('import time; time.sleep(1); raise SystemExit(9)', timeout=.4)
        self.assertEqual(update.state, 'running')
        update, _ = self.complete(console, update)
        self.assertEqual(update.state, 'failed')
        self.assertEqual(update.result.exitcode, 9)

    def test_observer_failure_leaves_successful_switch_owned_for_cleanup(self):
        console = self.console(credential_resolver=lambda _: SwitchCredentials(None),
                               switch_observer=lambda _: (_ for _ in ()).throw(RuntimeError('secret')))
        def simulated_switch(kind, *args, **kwargs):
            Console._console_layer(console, 'shell', 'bash')
            console.current.kind = kind
        with patch.object(console, '_console_layer', side_effect=simulated_switch):
            update = console.submit('$.sudo()')
        self.assertEqual(update.error_type, 'RuntimeError')
        self.assertEqual(len(console.environments), 2)
        self.assertNotIn('secret', update.stderr)

    def test_mock_target_retains_jump_and_login_identity(self):
        # Local channels simulate a connected target; no SSH login occurs here.
        parent, target = self.session(), self.session()
        target.host, target.username = 'simulated-target', 'login-user'
        with patch.object(parent, 'close', wraps=parent.close) as parent_close:
            with Console(target) as console:
                environment = console.environments[-1]
                self.assertEqual(environment.connection_user, 'login-user')
                self.assertEqual(environment.host, 'simulated-target')
                self.assertNotEqual(environment.effective_user, 'login-user')
            parent_close.assert_not_called()
        self.assertFalse(target.closed)

    def test_job_input_is_rejected_and_program_eof(self):
        console = self.console()
        console.start_command('sleep 30', timeout=3)
        with self.assertRaisesRegex(RuntimeError, 'use enter'):
            console.send_input('answer')
        console.interrupt()
        console.enter(shlex.quote(sys.executable) + ' -q -u', prompt='>>>', exit='quit()')
        update = console.send_input('print("raw-reply")\n', newline=False)
        update, output = self.complete(console, update)
        self.assertEqual(update.state, 'waiting_input')
        self.assertIn('raw-reply', output)
        console.eof()
        self.assertEqual(len(console.environments), 1)
        self.assertFalse(console.done)

    def test_unknown_job_recovery_and_host_exception_are_both_visible(self):
        console = Console(self.session())
        console.start_command('sleep 30', timeout=5, stop_timeout=1)
        with patch.object(console._job, 'stop', side_effect=RuntimeError('private')):
            update = console.interrupt()
        self.assertEqual(update.session_reuse, 'unknown')
        with self.assertRaises(BaseExceptionGroup) as caught:
            with console:
                raise ValueError('host failure')
        self.assertEqual([type(error) for error in caught.exception.exceptions],
                         [ValueError, ConsoleCleanupError])

    def test_dollar_start_is_tracked_and_cleanup_catches_silent_channel_failure(self):
        console = self.console()
        update = console.submit('job = $.start("sleep 30", timeout=3)')
        self.assertEqual(update.state, 'running')
        self.assertEqual(console.interrupt().result.stop_reason, 'cancelled')
        session = self.session()
        broken = Console(session)
        broken.current.console.channel.fail(ConnectionError('secret'))
        with self.assertRaises(ConsoleCleanupError):
            broken.close()
        self.assertEqual(broken.session_reuse, 'unknown')
        self.assertFalse(session.closed)

    def test_quit_preserves_final_output_once_and_input_clears_stale_status(self):
        console = self.console()
        update = console.submit('print("final-output"); quit()')
        self.assertEqual(update.state, 'closed')
        self.assertIn('final-output', update.stdout)
        self.assertEqual(console.poll().stdout, '')
        console = self.console()
        console.enter(shlex.quote(sys.executable) + ' -q -u', prompt='>>>', exit='quit()')
        update = console.send_input('import time; time.sleep(1)', timeout=.4)
        self.assertEqual(update.error_type, 'TimeoutError')
        update, _ = self.complete(console, update)
        self.assertEqual(update.state, 'waiting_input')
        update = console.send_input('print("next-input")', timeout=2)
        self.assertIsNone(update.error_type)
        self.assertIsNone(update.result)
        console.eof()

    def test_single_public_core_and_removed_legacy_entry_points(self):
        import interactive
        self.assertIs(interactive.Console, Console)
        self.assertFalse(hasattr(interactive, 'InteractiveConsole'))
        self.assertFalse(hasattr(Console, 'open'))
        self.assertFalse(hasattr(Console, 'execute'))
        console = self.console()
        for alias in (':help', ':quit'):
            self.assertEqual(console.submit(alias).state, 'failed')
            self.assertFalse(console.done)

    def test_terminal_and_host_use_identical_safe_diagnostics(self):
        diagnostics = []
        for terminal in (False, True):
            output, errors = io.StringIO(), io.StringIO()
            with Console(self.session(), terminal=terminal, stdout=output, stderr=errors) as console:
                for source in ('unknown_python_name', 'password="private"; broken=)',
                               'raise SystemExit("private")'):
                    self.assertEqual(console.submit(source).state, 'failed')
            self.assertNotIn('private', errors.getvalue())
            diagnostics.append(errors.getvalue())
        self.assertEqual(*diagnostics)

    def test_terminal_mode_without_tty_never_prompts_for_missing_credentials(self):
        console = self.console(terminal=True, stdout=io.StringIO(), stderr=io.StringIO())
        with patch('interactive.sys.stdin.isatty', return_value=False), \
             patch('interactive.getpass', side_effect=AssertionError('hidden password prompt')):
            for source in ('$.sudo()', 'getpass()'):
                self.assertEqual(console.submit(source).error_type, 'CredentialsRequiredError')

    def test_cli_constructs_public_core_with_owned_session(self):
        import interactive
        with patch('interactive.Console', wraps=Console) as factory, \
             patch('builtins.input', return_value='quit'), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(interactive.main([]), 0)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs, {'ownership': 'owned', 'terminal': True})
        self.assertTrue(factory.call_args.args[0].closed)

    def test_cli_drains_public_foreground_job_and_reports_failure(self):
        root = Path(__file__).resolve().parents[1]
        cli = subprocess.run([sys.executable, '-B', str(root / 'sshscript.py'), 'console'],
                             input='$.start("printf streamed; false", timeout=3)\nquit\n',
                             text=True, capture_output=True, timeout=20)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn('streamed', cli.stdout)
        self.assertIn('[exit 1]', cli.stderr)

    def test_thread_affinity(self):
        console = self.console()
        errors = []
        def other():
            try:
                console.close()
            except RuntimeError as error:
                errors.append(error)
        thread = threading.Thread(target=other)
        thread.start()
        thread.join(2)
        self.assertEqual(len(errors), 1)
        self.assertFalse(console.done)

    def test_terminal_handover_uses_existing_session(self):
        session = self.session()
        lines = iter(['answer=42', '$printf terminal-value', 'quit'])
        output = io.StringIO()
        with Console(session, terminal=True, input_func=lambda _: next(lines), stdout=output) as console:
            console.interact()
        self.assertIn('terminal-value', output.getvalue())
        self.assertEqual(console.session_reuse, 'confirmed')
