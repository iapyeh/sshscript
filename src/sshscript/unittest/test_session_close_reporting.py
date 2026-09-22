"""Tests that session cleanup failures cannot masquerade as success."""

import unittest

from session import Session


class FailingSocket:
    def close(self):
        raise OSError('simulated socket close failure')


class SessionCloseReportingTests(unittest.TestCase):
    def test_best_effort_close_reports_and_retains_failures(self):
        session = Session()
        session._sock = FailingSocket()

        result = session.close()

        self.assertFalse(result)
        self.assertTrue(session.closed)
        self.assertEqual(len(session.close_errors), 1)
        self.assertEqual(session.close_errors[0][0], 'close SSH socket')
        self.assertIsInstance(session.close_errors[0][1], OSError)
        self.assertFalse(session.close())

    def test_strict_close_raises_after_finishing_cleanup(self):
        session = Session()
        session._sock = FailingSocket()

        with self.assertRaisesRegex(
            RuntimeError,
            'session cleanup failed.*close SSH socket',
        ):
            session.close(strict=True)

        self.assertTrue(session.closed)
        self.assertIsNone(session._sock)
        with self.assertRaises(RuntimeError):
            session.close(strict=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
