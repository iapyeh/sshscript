"""Credential-free regression tests for SSHScript's logging API."""

from io import StringIO
import logging
from types import SimpleNamespace
import unittest
from uuid import uuid4

import channelgeneric
import errorutils
from channelgeneric import GenericChannel
from sessionwrapper import SessionWrapper


class TTYStream(StringIO):
    def isatty(self):
        return True


class LoggerCoreTests(unittest.TestCase):
    def make_wrapped_logger(self):
        """Create an isolated wrapper without replacing the process singleton."""
        original_logger = errorutils.logger
        raw_logger = logging.getLogger(f'sshscript.test.{uuid4().hex}')
        raw_logger.handlers.clear()
        raw_logger.propagate = True

        errorutils.logger = None
        try:
            wrapped = errorutils.WrappedLogger(raw_logger)
        finally:
            errorutils.logger = original_logger
        self.addCleanup(raw_logger.handlers.clear)
        return wrapped, raw_logger

    def test_library_logger_starts_with_null_handler_and_propagation(self):
        _, raw_logger = self.make_wrapped_logger()

        self.assertTrue(raw_logger.propagate)
        self.assertEqual(len(raw_logger.handlers), 1)
        self.assertIsInstance(raw_logger.handlers[0], logging.NullHandler)

    def test_explicit_tty_handler_is_formatted_and_not_duplicated(self):
        wrapped, raw_logger = self.make_wrapped_logger()
        stream = TTYStream()

        first = wrapped.dump_to_tty(stream)
        second = wrapped.dump_to_tty(stream)
        wrapped.warning('operation=%s', 'retry')

        self.assertIs(first, second)
        self.assertFalse(raw_logger.propagate)
        self.assertEqual(
            sum(
                isinstance(handler, logging.StreamHandler)
                and not isinstance(handler, logging.NullHandler)
                for handler in raw_logger.handlers
            ),
            1,
        )
        output = stream.getvalue()
        self.assertIn('WARNING', output)
        self.assertIn(raw_logger.name, output)
        self.assertIn('[thread=', output)
        self.assertIn('operation=retry', output)

        wrapped.mute_tty()
        wrapped.mute_tty()
        self.assertNotIn(first, raw_logger.handlers)
        self.assertTrue(raw_logger.propagate)

    def test_console_handler_supports_redirected_stderr(self):
        wrapped, raw_logger = self.make_wrapped_logger()
        stream = StringIO()

        first = wrapped.add_console_handler(stream)
        second = wrapped.add_console_handler(stream)
        wrapped.error('operation=%s', 'failed')

        self.assertIs(first, second)
        self.assertFalse(raw_logger.propagate)
        self.assertIn('ERROR', stream.getvalue())
        self.assertIn('operation=failed', stream.getvalue())

    def test_log_debug_preserves_lazy_formatting_arguments(self):
        class RecordingLogger:
            def __init__(self):
                self.call = None

            def debug(self, message, *args, **kwargs):
                self.call = (message, args, kwargs)

        marker = object()
        recorder = RecordingLogger()
        original_logger = errorutils.logger
        errorutils.logger = recorder
        try:
            errorutils.log_debug(
                'marker=%s',
                marker,
                extra={'session_id': 'test'},
            )
        finally:
            errorutils.logger = original_logger

        self.assertEqual(recorder.call[0], 'marker=%s')
        self.assertIs(recorder.call[1][0], marker)
        self.assertEqual(
            recorder.call[2],
            {'extra': {'session_id': 'test'}},
        )

    def test_level_eight_api_is_removed(self):
        self.assertFalse(hasattr(errorutils, 'DEBUG8'))
        self.assertFalse(hasattr(errorutils, 'log_debug_8'))

    def test_sensitive_values_are_redacted(self):
        private_key = (
            '-----BEGIN RSA PRIVATE KEY-----\n'
            'private-material\n'
            '-----END RSA PRIVATE KEY-----'
        )
        text = (
            'password=hunter2 token="api token" '
            'Authorization: Bearer bearer-token '
            'https://alice:url-secret@example.test/path '
            '--client-secret cli-secret '
            f'{private_key}'
        )

        redacted = errorutils.redact_sensitive(text)

        for secret in (
            'hunter2',
            'api token',
            'bearer-token',
            'url-secret',
            'cli-secret',
            'private-material',
        ):
            self.assertNotIn(secret, redacted)
        self.assertIn('password=<redacted>', redacted)
        self.assertIn('Authorization: Bearer <redacted>', redacted)
        self.assertIn('<redacted-private-key>', redacted)

    def test_command_summary_omits_arguments(self):
        secret = 'must-not-appear'
        summary = errorutils.command_summary(
            f'/usr/bin/python3 --password {secret}'
        )

        self.assertEqual(
            summary,
            {
                'type': 'str',
                'executable': 'python3',
                'char_count': len(
                    f'/usr/bin/python3 --password {secret}'
                ),
                'arg_count': 3,
            },
        )
        self.assertNotIn(secret, repr(summary))

    def test_level_below_debug_is_normalized(self):
        wrapped, raw_logger = self.make_wrapped_logger()

        wrapped.reset_debug(8)

        self.assertEqual(raw_logger.level, logging.DEBUG)


class SessionWrapperLoggerTests(unittest.TestCase):
    def test_logger_property_and_level_forwarding(self):
        session_logger = object()

        class RecordingChannel:
            def __init__(self):
                self.owner = SimpleNamespace(
                    session=SimpleNamespace(logger=session_logger)
                )
                self.call = None

            def log(self, message, *args, **kwargs):
                self.call = (message, args, kwargs)
                return 'logged'

        channel = RecordingChannel()
        wrapper = SessionWrapper(SimpleNamespace(channel=channel))

        self.assertIs(wrapper.logger, session_logger)
        result = wrapper.log(
            logging.WARNING,
            'attempt=%d',
            2,
            extra={'session_id': 'test'},
        )

        self.assertEqual(result, 'logged')
        self.assertEqual(channel.call[0], 'attempt=%d')
        self.assertEqual(channel.call[1], (2,))
        self.assertEqual(
            channel.call[2],
            {
                'level': logging.WARNING,
                'extra': {'session_id': 'test'},
            },
        )

    def test_legacy_numeric_level_below_debug_is_normalized(self):
        class RecordingLogger:
            def __init__(self):
                self.level = None

            def log(self, level, *args, **kwargs):
                self.level = level

        recorder = RecordingLogger()
        original_logger = channelgeneric.logger
        channelgeneric.logger = recorder
        try:
            channel = object.__new__(GenericChannel)
            channel.prefixOfLog = '[TestChannel]'
            channel.log('legacy-level', level=8)
        finally:
            channelgeneric.logger = original_logger

        self.assertEqual(recorder.level, logging.DEBUG)


if __name__ == '__main__':
    unittest.main(verbosity=2)
