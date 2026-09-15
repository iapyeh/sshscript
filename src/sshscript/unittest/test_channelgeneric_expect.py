"""Regression tests for interactive expect dialog synchronization."""

from pathlib import Path
import sys
import threading
import time
import unittest


SOURCE_ROOT = Path(__file__).resolve().parent.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from channelgeneric import GenericChannel


class RecordingChannel(GenericChannel):
    def __init__(self):
        super().__init__(owner=None)
        self.sent = []
        self.sent_event = threading.Event()
        self._set_open()

    def send(self, text, timeout=None):
        self.sent.append(text)
        self.sent_event.set()
        return len(text)

    def close_test_buffers(self):
        for stdout, stderr in self.stdio_store:
            stdout.close()
            stderr.close()


class InteractiveExpectTests(unittest.TestCase):
    def setUp(self):
        self.channel = RecordingChannel()
        self.addCleanup(self.channel.close_test_buffers)

    def test_password_dialog_waits_for_configured_prompt(self):
        self.channel.prompt = "mysql>"
        outcome = {}

        def run_expect():
            outcome["result"] = self.channel.expect(
                {"password": "dbpassword"},
                timeout=2,
            )

        waiter = threading.Thread(target=run_expect)
        waiter.start()
        self.channel._stdout.append("Enter password:")

        self.assertTrue(self.channel.sent_event.wait(1))
        self.assertEqual(self.channel.sent, ["dbpassword\n"])

        # Sending the response is not authentication completion.  expect()
        # must remain blocked until the interactive program is actually ready.
        time.sleep(0.05)
        self.assertTrue(waiter.is_alive())

        for chunk in ("\r\nWelcome\r\n", "my", "sql", ">"):
            self.channel._stdout.append(chunk)

        waiter.join(1)
        self.assertFalse(waiter.is_alive())
        self.assertIn("password", outcome["result"])

    def test_dialog_without_prompt_keeps_immediate_return_behavior(self):
        outcome = {}

        def run_expect():
            outcome["result"] = self.channel.expect(
                {"question": "answer"},
                timeout=1,
            )

        waiter = threading.Thread(target=run_expect)
        waiter.start()
        self.channel._stdout.append("question")
        waiter.join(1)

        self.assertFalse(waiter.is_alive())
        self.assertEqual(self.channel.sent, ["answer\n"])
        self.assertIn("question", outcome["result"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
