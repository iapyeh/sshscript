"""Exception and atomic-state contracts, also executed with python -O."""
from pathlib import Path
import re
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from channelgeneric import GenericChannel
from channelsubprocess import POpenChannel
from dollar import Dollar
from errorutils import SSHScriptException
from patching import SshscriptStack
from session import Session
from stdio import SSHScriptStdout
from check_package_asserts import violations


class ProductionContractTests(unittest.TestCase):
    def exact_error(self, cls, fragment, fn):
        with self.assertRaisesRegex(cls, fragment) as caught:
            fn()
        self.assertIs(type(caught.exception), cls)

    def buffer(self):
        buf = SSHScriptStdout()
        self.addCleanup(buf.close)
        return buf

    def channel(self):
        channel = GenericChannel(None)
        for pair in channel.stdio_store:
            for buf in pair:
                self.addCleanup(buf.close)
        return channel

    def test_package_has_no_assert_nodes(self):
        self.assertEqual(violations(), [])

    def test_listener_identity_and_atomic_removal(self):
        buf = self.buffer()
        class Listener:
            def __call__(self, item): pass
            def __eq__(self, other): return True
        first, second = Listener(), Listener()
        self.exact_error(RuntimeError, 'empty', lambda: buf.pop_listener(first))
        buf.push_listener(first)
        self.exact_error(RuntimeError, 'not on top', lambda: buf.pop_listener(second))
        self.assertEqual(len(buf._listeners), 1)
        self.assertIs(buf._listeners[-1], first)
        buf.push_listener(second)
        self.exact_error(RuntimeError, 'not on top', lambda: buf.pop_listener(first))
        self.assertIs(buf._listeners[-1], second)
        buf.pop_listener(second)
        buf.pop_listener(first)
        self.assertEqual(buf._listeners, [])

    def test_hijack_restores_mapping_without_failure_mutation(self):
        ch = self.channel()
        original = ch.send_line
        self.exact_error(RuntimeError, 'release hijack twice', lambda: ch.hijack(False))
        self.assertEqual(ch.send_line, original)
        ch.hijack(True)
        state = (ch.send_line, ch._send_line, ch.hijacked)
        self.exact_error(RuntimeError, 'hijack twice', lambda: ch.hijack(True))
        self.assertEqual((ch.send_line, ch._send_line, ch.hijacked), state)
        ch.hijack(False)
        self.assertEqual(ch.send_line, original)
        self.assertIsNone(ch._send_line)
        self.assertFalse(ch.hijacked)
        self.exact_error(RuntimeError, 'release hijack twice', lambda: ch.hijack(False))
        self.assertEqual(ch.send_line, original)

    def test_last_layer_preserves_all_state(self):
        ch = self.channel()
        ch.prompt = 'prompt'
        ch._stdout.append('retained')
        ch._exited_interactive_layers.add(ch.executing_lock)
        state = (list(ch.prompts), list(ch.executing_locks), list(ch.stdio_store), set(ch._exited_interactive_layers))
        self.exact_error(RuntimeError, 'last channel layer', ch.decrease_layer)
        self.assertEqual((ch.prompts, ch.executing_locks, ch.stdio_store, ch._exited_interactive_layers), state)
        self.assertEqual(str(ch._stdout), 'retained')

    def test_disconnected_sftp(self):
        session = Session()
        self.addCleanup(session.close)
        self.exact_error(SSHScriptException, 'active SSH connection', lambda: session.sftp)

    def test_stack_indices(self):
        stack = SshscriptStack(threading.current_thread(), ['a', 'b', 'c'])
        for index, value in [(0,'a'), (1,'b'), (2,'c'), (-1,'c'), (-3,'a')]:
            self.assertEqual(stack[index], value)
        for index in (3, 4, -4):
            self.exact_error(IndexError, 'index out of range', lambda: stack[index])
        empty = SshscriptStack(threading.current_thread())
        self.exact_error(IndexError, 'index out of range', lambda: empty[0])

    def test_command_validation_before_execution(self):
        session = Session()
        self.addCleanup(session.close)
        with patch('dollar.subprocess.Popen') as popen, patch('dollar.subprocess.run') as run, patch('dollar.threading.Thread') as thread:
            for value in (1, 'yes', None, [], {}):
                self.exact_error(TypeError, 'for_with must be bool', lambda: Dollar(session, 'echo ok', for_with=value))
            for value in (None, 1, [], b'echo'):
                self.exact_error(TypeError, 'command must be str', lambda: Dollar(session, value))
            for value in ('', '   '):
                self.exact_error(ValueError, 'empty', lambda: Dollar(session, value))
            self.exact_error(ValueError, 'single line', lambda: Dollar(session, 'echo a\necho b', for_with=True))
            for value in (1, 'yes', [], {}):
                dollar = Dollar(session, 'echo ok')
                self.exact_error(TypeError, 'get_pty', lambda: dollar(value))
                self.assertIsNone(dollar.channel)
                dollar = Dollar(session, 'echo ok', get_pty=value)
                self.exact_error(TypeError, 'get_pty', dollar)
                self.exact_error(TypeError, 'get_pty', lambda: session.shell(get_pty=value))
            popen.assert_not_called()
            run.assert_not_called()
            thread.assert_not_called()

    def test_parent_pty_and_descriptor_types(self):
        for value in (1, 'parent', object()):
            self.exact_error(
                TypeError,
                'parent must be Session',
                lambda value=value: Session(value),
            )

        session = Session()
        self.addCleanup(session.close)
        for value in (1, 'yes', [], {}):
            for call in (
                lambda value=value: session.su('nobody', get_pty=value),
                lambda value=value: session.sudo(get_pty=value),
                lambda value=value: session.enter('python3', get_pty=value),
            ):
                self.exact_error(TypeError, 'get_pty', call)

        with patch(
            'channelsubprocess.GenericChannel.__init__',
            return_value=None,
        ) as channel_init:
            process = object()
            for value in (1, 'yes', [], {}):
                self.exact_error(
                    TypeError,
                    'get_pty must be None or bool',
                    lambda value=value: POpenChannel(
                        None, process, [], None, [], value
                    ),
                )
            self.exact_error(
                TypeError,
                'stdouterr must be list',
                lambda: POpenChannel(
                    None, process, (1,), None, [], True
                ),
            )
            for get_pty, descriptors in (
                (True, []),
                (True, [1, 2]),
                (False, []),
                (False, [1]),
            ):
                self.exact_error(
                    ValueError,
                    'descriptor',
                    lambda get_pty=get_pty, descriptors=descriptors: POpenChannel(
                        None, process, descriptors, None, [], get_pty
                    ),
                )
            channel_init.assert_not_called()
            channel = POpenChannel(
                None, process, [1, 2], None, [], None
            )
            self.assertIs(channel.get_pty, False)
            channel_init.assert_called_once_with(None)

    def test_buffers_and_patterns_validate_before_mutation(self):
        ch = self.channel()
        buf = ch._stdout
        buf.append('original')
        callback = lambda: None
        buf.set_callback(callback, 'marker')
        for value in (b'bad', 1, None):
            self.exact_error(TypeError, 'must be str', lambda: buf.append(value))
        self.exact_error(TypeError, 'output item', lambda: buf.__setitem__(0, 1))
        self.assertEqual(str(buf), 'original')
        for value in (["not", "text"], 1, object()):
            self.exact_error(
                TypeError,
                'initial output',
                lambda value=value: SSHScriptStdout(value),
            )
        self.exact_error(TypeError, 'pattern', lambda: buf.set_callback(None, re.compile(b'x')))
        self.assertIs(buf.callback, callback)
        self.assertEqual(buf.callback_pattern, 'marker')
        for method in (ch.expect, ch.expect_old):
            self.exact_error(TypeError, 'bytes regular', lambda: method(re.compile(b'x')))
        self.exact_error(TypeError, 'command must be str', lambda: ch.send_command(1))
        self.exact_error(ValueError, 'empty', lambda: ch.send_command(' '))
        self.assertEqual(str(buf), 'original')
        self.assertEqual(buf._listeners, [])
        self.assertFalse(ch.executing_lock.locked())

    def test_migrated_stdio_string_operations(self):
        buf = self.buffer()
        self.assertFalse(buf)
        for chunk in ('that', 'is', 'an', 'book'): buf.append(chunk)
        self.assertTrue(buf)
        buf[0] = 'this'
        self.assertIn('this', buf)
        self.assertEqual(buf[1], 'is')
        self.assertEqual(buf, 'thisisanbook')
        self.assertEqual('thisisanbook', buf)
        self.assertEqual(','.join(buf), 'this,is,an,book')
        self.assertEqual(buf + 'ok', 'thisisanbookok')
        self.assertEqual('ok' + buf, 'okthisisanbook')
        self.assertEqual(buf.strip(), 'thisisanbook')
        self.assertEqual(buf.join(['-']), '-')
        self.assertEqual(buf.join(['-', '-']), '-thisisanbook-')
        self.assertEqual(len(buf), 4)
        self.assertTrue(all(len(chunk) > 1 for chunk in buf))
        self.assertEqual(buf, 'thisisanbook')
        self.assertEqual(list(buf(0.02, True)), ['this', 'is', 'an', 'book'])
        self.assertEqual(buf, '')

    def test_closed_and_hijacked_channel_exceptions(self):
        ch = self.channel()
        ch._set_open()
        ch.hijack(True)
        self.exact_error(RuntimeError, 'hijacked', ch.get_exit_code)
        self.exact_error(RuntimeError, 'hijacked', lambda: GenericChannel.send_line(ch, 'echo ok'))
        ch.hijack(False)
        ch._finish_close()
        self.exact_error(BrokenPipeError, 'closed', ch.get_exit_code)

        failed = self.channel()
        failed._set_open()
        failure = ConnectionError('transport failed')
        failed.fail(failure)
        with self.assertRaises(ConnectionError) as caught:
            failed.get_exit_code()
        self.assertIs(caught.exception, failure)
        buf = self.buffer()
        buf.close()
        self.exact_error(BrokenPipeError, 'closed', lambda: buf.append('x'))

    def test_session_shell_rejects_invalid_values_without_execution(self):
        session = Session()
        self.addCleanup(session.close)
        with patch('session.Dollar') as dollar:
            self.exact_error(TypeError, 'funcname must be str', lambda: session.shell(funcname=1))
            self.exact_error(ValueError, 'invalid console funcname', lambda: session.shell(funcname='bad'))
            self.exact_error(TypeError, 'command must be str', lambda: session.shell(command=1))
            self.exact_error(ValueError, 'empty', lambda: session.shell(command=' '))
            self.exact_error(ValueError, 'single line', lambda: session.shell(command='bash\nsh'))
            self.exact_error(ValueError, 'single line', lambda: session.shell(command='bash\rsh'))
            dollar.assert_not_called()

    def test_all_persistent_command_entry_points_validate_first(self):
        session = Session()
        self.addCleanup(session.close)
        for value in (None, 1, [], {}):
            self.exact_error(
                TypeError,
                'command must be str',
                lambda value=value: session.enter(value),
            )
        for value in ('', '   '):
            self.exact_error(
                ValueError,
                'empty',
                lambda value=value: session.enter(value),
            )
        for value in ('python3\n-i', 'python3\r-i'):
            self.exact_error(
                ValueError,
                'single line',
                lambda value=value: session.enter(value),
            )

        class Console:
            channel = object()

        from sessionwrapper import SessionWrapper
        wrapper = SessionWrapper(Console())
        for value in (None, 1, [], {}):
            self.exact_error(
                TypeError,
                'command must be str',
                lambda value=value: wrapper.enter(value),
            )
        for value in ('', '   '):
            self.exact_error(
                ValueError,
                'empty',
                lambda value=value: wrapper.enter(value),
            )
            self.exact_error(
                ValueError,
                'empty',
                lambda value=value: wrapper.shell(value),
            )
        for value in ('bash\nsh', 'bash\rsh'):
            self.exact_error(
                ValueError,
                'single line',
                lambda value=value: wrapper.shell(value),
            )
            self.exact_error(
                ValueError,
                'single line',
                lambda value=value: wrapper.enter(value),
            )
        for value in (1, [], {}, True):
            for call in (
                lambda value=value: wrapper.su('nobody', command=value),
                lambda value=value: wrapper.sudo('secret', command=value),
            ):
                self.exact_error(TypeError, 'command must be str', call)
        for value in ('', '   '):
            for call in (
                lambda value=value: wrapper.su('nobody', command=value),
                lambda value=value: wrapper.sudo('secret', command=value),
            ):
                self.exact_error(ValueError, 'empty', call)
        for value in ('su\nsh', 'sudo\rsh'):
            for call in (
                lambda value=value: wrapper.su('nobody', command=value),
                lambda value=value: wrapper.sudo('secret', command=value),
            ):
                self.exact_error(ValueError, 'single line', call)
        for value in (1, 'yes', [], {}):
            for call in (
                lambda value=value: wrapper.su('nobody', get_pty=value),
                lambda value=value: wrapper.sudo('secret', get_pty=value),
                lambda value=value: wrapper.enter('python3', get_pty=value),
            ):
                self.exact_error(TypeError, 'get_pty', call)

    def test_ast_parent_mismatches_are_runtime_errors(self):
        import ast
        from dollarchanger import DollarChanger

        changer = DollarChanger()
        changer.currentExpr = ast.parse('different()').body[0]
        call = ast.parse(
            "_sshscript_in_context_.connect('host')"
        ).body[0].value
        self.exact_error(
            RuntimeError,
            'AST parent content',
            lambda: changer.generic_visit(call),
        )

        changer = DollarChanger()
        current = ast.parse(
            "_sshscript_in_context_.connect('host')"
        ).body[0]
        current.parent = ast.If(
            test=ast.Constant(value=True),
            body=[],
            orelse=[],
        )
        changer.currentExpr = current
        self.exact_error(
            RuntimeError,
            'parent body',
            lambda: changer.generic_visit(current.value),
        )
