"""Syntax validation must never execute user code, imports, or commands."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import sshscript


class CheckFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'script.spy'

    def test_check_does_not_create_session_execute_commands_or_import(self):
        self.path.write_text('import module_that_does_not_exist\nraise RuntimeError("executed")\n$touch must-not-exist\n')
        with patch.object(sshscript, 'Session', side_effect=AssertionError('created session')), \
             patch('subprocess.Popen', side_effect=AssertionError('started subprocess')):
            self.assertEqual(sshscript.check_file(self.path), 0)

    def test_cli_success_is_offline_and_leaves_no_side_effect(self):
        marker = Path(self.folder.name) / 'executed'
        self.path.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\nimport nonexistent_module\n$false\n')
        result = self.cli('--check', str(self.path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(result.stdout, '')

    def cli(self, *args):
        return subprocess.run([sys.executable, sshscript.__file__, *args],
                              text=True, capture_output=True, timeout=20)

    def test_errors_show_original_source_and_location(self):
        for source, line in [('if True\n    $echo unreachable\n', 1),
                             ('def f():\n    $(\n', 2),
                             ('with $.unsupported_context():\n    pass\n', 1),
                             ('return 1\n', 1),
                             ('if True:\n    x=1\n  y=2\n', 3)]:
            with self.subTest(source=source):
                self.path.write_text(source)
                result = self.cli('--check', str(self.path))
                self.assertEqual(result.returncode, 1)
                self.assertIn(f'File "{self.path}", line {line}', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertNotIn('dollarparser.py', result.stderr)

    def test_check_handles_python_and_rejects_extra_files(self):
        self.path.write_text('x = 1\n')
        self.assertEqual(self.cli('--check', str(self.path), str(self.path)).returncode, 2)
        self.assertEqual(self.cli('--check', '--script', str(self.path)).returncode, 2)
        python = self.path.with_suffix('.py')
        python.write_text('raise RuntimeError("must not run")\n')
        self.assertEqual(sshscript.check_file(python), 0)


if __name__ == '__main__':
    unittest.main()
