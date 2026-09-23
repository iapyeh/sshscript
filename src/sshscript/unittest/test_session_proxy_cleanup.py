"""Regression tests for orderly Paramiko ProxyCommand shutdown."""

from pathlib import Path
import logging
import shlex
import sys
import threading
import unittest

import paramiko


SOURCE_ROOT = Path(__file__).resolve().parent.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from session import Session, _IdempotentProxyCommand


class ProxyShutdownTests(unittest.TestCase):
    def test_proxy_eof_stops_reader_before_streams_are_closed(self):
        proxy = _IdempotentProxyCommand(shlex.join([
            sys.executable,
            '-c',
            'import time; time.sleep(30)',
        ]))
        session = object.__new__(Session)
        session.closed = True
        result = {}
        entered = threading.Event()

        def read_proxy():
            entered.set()
            try:
                result['value'] = proxy.recv(1)
            except BaseException as exc:
                result['exception'] = exc

        reader = threading.Thread(target=read_proxy)
        reader.start()
        self.assertTrue(entered.wait(1))

        complete, forced_kill, errors = session._cleanup_proxy_command(
            proxy,
            transport=reader,
        )

        reader.join(1)
        self.assertFalse(reader.is_alive())
        self.assertNotIn('exception', result)
        self.assertEqual(result.get('value'), b'')
        self.assertTrue(complete)
        self.assertFalse(forced_kill)
        self.assertEqual(errors, [])
        self.assertIsNotNone(proxy.process.poll())
        self.assertTrue(proxy.process.stdin.closed)
        self.assertTrue(proxy.process.stdout.closed)
        self.assertTrue(proxy.process.stderr.closed)

    def test_session_close_stops_real_paramiko_transport_cleanly(self):
        self._check_transport_shutdown(banner_delay=0)

    def test_session_close_waits_for_delayed_banner_before_shutdown(self):
        # Exceed multiple socket read timeouts: a repeated recv alone does
        # not imply that the SSH banner has been parsed.
        self._check_transport_shutdown(banner_delay=0.4)

    def _check_transport_shutdown(self, banner_delay):
        child = (
            "import sys,time; "
            f"time.sleep({banner_delay}); "
            "sys.stdout.write('SSH-2.0-fake\\r\\n'); "
            "sys.stdout.flush(); "
            "time.sleep(30)"
        )
        proxy = _IdempotentProxyCommand(shlex.join([
            sys.executable,
            '-c',
            child,
        ]))
        reading_after_banner = threading.Event()
        recv_calls = [0]
        original_recv = proxy.recv

        def observed_recv(size):
            recv_calls[0] += 1
            # Signal a read after banner parsing, not a timeout retry while
            # still waiting for the child to emit its first bytes.
            if transport.remote_version:
                reading_after_banner.set()
            return original_recv(size)

        proxy.recv = observed_recv
        transport = paramiko.Transport(proxy)
        transport.banner_timeout = 3

        class FakeClient:
            def __init__(self, active_transport):
                self._transport = active_transport

            def get_transport(self):
                return self._transport

            def close(self):
                if self._transport is not None:
                    self._transport.close()
                    self._transport = None

        records = []

        class RecordHandler(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = RecordHandler()
        paramiko_logger = logging.getLogger('paramiko.transport')
        paramiko_logger.addHandler(handler)

        session = None
        try:
            transport.start_client(event=threading.Event())
            self.assertTrue(
                reading_after_banner.wait(5),
                (recv_calls[0], transport.is_alive(),
                 transport.remote_version, transport.saved_exception,
                 [record.getMessage() for record in records]),
            )
            self.assertEqual(transport.remote_version, 'SSH-2.0-fake')

            session = Session()
            session._host = 'fake-host'
            session._port = 22
            session._username = 'fake-user'
            session._sock = proxy
            session._client = FakeClient(transport)
            session.close()

            transport.join(2)
            self.assertFalse(transport.is_alive())
            self.assertNotIsInstance(
                transport.saved_exception,
                ValueError,
            )
            errors = [
                record.getMessage() for record in records
                if record.levelno >= logging.ERROR
                or 'Unknown exception' in record.getMessage()
                or 'I/O operation on closed file' in record.getMessage()
            ]
            self.assertEqual(errors, [], '\n'.join(errors))
            self.assertIsNotNone(proxy.process.poll())
            self.assertTrue(proxy.process.stdin.closed)
            self.assertTrue(proxy.process.stdout.closed)
            self.assertTrue(proxy.process.stderr.closed)
        finally:
            paramiko_logger.removeHandler(handler)

            if transport.is_alive():
                try:
                    proxy.process.stdout.close()
                except BaseException:
                    pass
                transport.join(2)

            if proxy.process.poll() is None:
                proxy.process.kill()
                proxy.process.wait(timeout=2)

            for stream_name in ('stdin', 'stdout', 'stderr'):
                stream = getattr(proxy.process, stream_name, None)
                if stream is not None and not stream.closed:
                    stream.close()

            if session is not None and not session.closed:
                session.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
