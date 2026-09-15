"""Regression tests for the live string behavior of stdout/stderr buffers."""

from pathlib import Path
import sys
import threading
import unittest


SOURCE_ROOT = Path(__file__).resolve().parent.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from stdio import SSHScriptStdout


class DynamicStdoutStringTests(unittest.TestCase):
    def test_bound_splitlines_reads_content_at_call_time(self):
        stdout = SSHScriptStdout()
        self.addCleanup(stdout.close)
        splitlines = stdout.splitlines

        stdout.append("first\nsecond\n", splitlines=True)

        self.assertEqual(splitlines(), ["first", "second"])
        self.assertEqual(
            splitlines(keepends=True),
            ["first\n", "second\n"],
        )

    def test_splitlines_tracks_later_appends(self):
        stdout = SSHScriptStdout()
        self.addCleanup(stdout.close)
        stdout.append("first\n", splitlines=True)
        self.assertEqual(stdout.splitlines(), ["first"])

        stdout.append("second\n", splitlines=True)

        self.assertEqual(stdout.splitlines(), ["first", "second"])
        self.assertEqual(
            stdout.splitlines(),
            str(stdout).splitlines(),
        )

    def test_callback_matches_prompt_split_across_many_chunks(self):
        stdout = SSHScriptStdout()
        self.addCleanup(stdout.close)
        prompt_found = threading.Event()
        stdout.set_callback(prompt_found.set, "mysql>")

        for chunk in ("result\r\n", "m", "y", "s", "q", "l", ">"):
            stdout.append(chunk)

        self.assertTrue(prompt_found.is_set())
        self.assertEqual(str(stdout), "result\r\n")

    def test_callback_preserves_text_around_fragmented_prompt(self):
        stdout = SSHScriptStdout()
        self.addCleanup(stdout.close)
        prompt_found = threading.Event()
        stdout.set_callback(prompt_found.set, "mysql>")

        stdout.append("before-m")
        stdout.append("ys")
        stdout.append("ql>after")

        self.assertTrue(prompt_found.is_set())
        self.assertEqual(str(stdout), "before-after")


if __name__ == "__main__":
    unittest.main(verbosity=2)
