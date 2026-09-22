"""Regression tests for tracebacks produced from translated .spy files."""

import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import tokenize
import unittest
import uuid


SOURCE_ROOT = Path(__file__).resolve().parent.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import sshscript
import dollarparser


class SpySourceMappingTests(unittest.TestCase):
    def test_tokenizer_eof_wording_maps_to_unmatched_delimiter(self):
        for message in ('EOF in multi-line statement',
                        'unexpected EOF in multi-line statement'):
            with self.subTest(message=message):
                error = dollarparser._token_syntax_error(
                    tokenize.TokenError(message, (3, 0)),
                    'unfinished.spy', '\n$(\n',
                )
                self.assertEqual(error.filename, 'unfinished.spy')
                self.assertEqual(error.lineno, 2)
                self.assertEqual(error.offset, 2)
                self.assertEqual(error.text, '$(\n')

    def test_generated_with_targets_have_store_context(self):
        sources = (
            "with $:\n    pass\n",
            "with $bash:\n    pass\n",
            "with $.session.enter('command'):\n    pass\n",
            "with $.enter('command'):\n    pass\n",
        )

        for index, source in enumerate(sources):
            with self.subTest(source=source):
                dollarparser.compile_spy(f"with_target_{index}.spy", source)

    def test_unscoped_connect_uses_explicit_stack_activation(self):
        converted = dollarparser.convert(
            "unscoped_connect.spy",
            "$.connect('user@example.test')\n",
        )
        self.assertIn("connect_and_activate", converted)

    def run_failing_file(self, source, variables=None):
        temporary = tempfile.TemporaryDirectory(prefix="sshscript-mapping-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "source_mapping.spy"
        path.write_text(source, encoding="utf-8")

        try:
            sshscript.run_file(str(path), vars=variables)
        except BaseException as exception:
            return path, exception
        self.fail("script did not raise")

    def spy_frames(self, path, exception):
        return [
            frame
            for frame in traceback.extract_tb(exception.__traceback__)
            if frame.filename == str(path)
        ]

    def test_plain_python_runtime_error_uses_original_source(self):
        source = "first = 1\nsecond = 0\nvalue = first / second\n"
        path, exception = self.run_failing_file(source)

        frame = self.spy_frames(path, exception)[-1]
        self.assertEqual(frame.lineno, 3)
        self.assertEqual(frame.line, "value = first / second")

    def test_nested_dollar_expression_uses_original_source(self):
        def explode():
            raise RuntimeError("expected failure")

        source = (
            "def nested():\n"
            "    if True:\n"
            "        $f'{explode()}'\n"
            "nested()\n"
        )
        path, exception = self.run_failing_file(
            source, {"explode": explode}
        )

        frames = self.spy_frames(path, exception)
        self.assertEqual(frames[-1].lineno, 3)
        self.assertEqual(frames[-1].line, "$f'{explode()}'")
        self.assertEqual(frames[-2].lineno, 4)
        self.assertEqual(frames[-2].line, "nested()")

    def test_dollar_command_exception_uses_command_source_line(self):
        source = (
            "def nested():\n"
            "    if True:\n"
            "        $sshscript-source-map-command-does-not-exist\n"
            "nested()\n"
        )
        path, exception = self.run_failing_file(source)

        self.assertIsInstance(exception, FileNotFoundError)
        frame = self.spy_frames(path, exception)[-1]
        self.assertEqual(frame.lineno, 3)
        self.assertEqual(
            frame.line, "$sshscript-source-map-command-does-not-exist"
        )

    def test_multiline_dollar_expression_maps_inner_failing_line(self):
        def explode():
            raise RuntimeError("expected failure")

        source = (
            "def nested():\n"
            "    $(\n"
            "        explode()\n"
            "    )\n"
            "nested()\n"
        )
        path, exception = self.run_failing_file(
            source, {"explode": explode}
        )

        frame = self.spy_frames(path, exception)[-1]
        self.assertEqual(frame.lineno, 3)
        self.assertEqual(frame.line, "explode()")

    def test_syntax_error_uses_original_filename_line_and_text(self):
        source = "if True\n    $echo unreachable\n"
        path, exception = self.run_failing_file(source)

        self.assertIsInstance(exception, SyntaxError)
        self.assertEqual(exception.filename, str(path))
        self.assertEqual(exception.lineno, 1)
        self.assertEqual(exception.text, "if True\n")
        rendered = "".join(
            traceback.format_exception_only(type(exception), exception)
        )
        self.assertIn(str(path), rendered)
        self.assertIn("if True", rendered)
        self.assertNotIn("__pycache__", rendered)

    def test_tokenization_error_uses_original_filename_line_and_text(self):
        path, exception = self.run_failing_file("$(")

        self.assertIsInstance(exception, SyntaxError)
        self.assertEqual(exception.filename, str(path))
        self.assertEqual(exception.lineno, 1)
        self.assertEqual(exception.offset, 2)
        self.assertEqual(exception.text, "$(")

    def test_unclosed_list_comprehension_maps_to_opening_line(self):
        source = (
            "def get_mysql_state_on_master():\n"
            "    with $.connect(config['master']['account']):\n"
            "        with $.enter('mysql'):\n"
            "            $.expect('password')\n"
            "            $.input(config['master']['db']['passwd'])\n"
            "        if $.exitcode == 0:\n"
            "            for line in [x.strip() for x in "
            "$.stdout.splitlines():\n"
            "                if line.startswith('File:'):\n"
            "                    pass\n"
        )
        path, exception = self.run_failing_file(source)

        self.assertIsInstance(exception, SyntaxError)
        self.assertEqual(exception.filename, str(path))
        self.assertEqual(exception.lineno, 7)
        self.assertEqual(
            exception.text,
            "            for line in [x.strip() for x in "
            "$.stdout.splitlines():\n",
        )

    def test_cli_displays_mapped_syntax_error_without_traceback_flag(self):
        temporary = tempfile.TemporaryDirectory(prefix="sshscript-cli-mapping-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "syntax_error.spy"
        path.write_text(
            "def example():\n"
            "    with $.connect('example'):\n"
            "        pass\n"
            "    if True:\n"
            "        pass\n"
            "    else:\n"
            "        for line in [x.strip() for x in $.stdout.splitlines():\n"
            "            pass\n",
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, str(SOURCE_ROOT / "sshscript.py"), str(path)],
            cwd=SOURCE_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn(f'File "{path}", line 7', completed.stderr)
        self.assertIn(
            "for line in [x.strip() for x in $.stdout.splitlines():",
            completed.stderr,
        )
        self.assertNotIn("__pycache__", completed.stderr)
        self.assertNotIn("dollarparser.py", completed.stderr)

    def test_translation_error_uses_original_filename_line_and_text(self):
        source = "with $.unsupported_context():\n    pass\n"
        path, exception = self.run_failing_file(source)

        self.assertIsInstance(exception, SyntaxError)
        self.assertEqual(exception.filename, str(path))
        self.assertEqual(exception.lineno, 1)
        self.assertEqual(exception.text, "with $.unsupported_context():\n")

    def test_imported_spy_runtime_error_uses_original_source(self):
        temporary = tempfile.TemporaryDirectory(prefix="sshscript-import-")
        self.addCleanup(temporary.cleanup)
        module_name = "mapped_spy_" + uuid.uuid4().hex
        path = Path(temporary.name) / f"{module_name}.spy"
        path.write_text(
            "def nested():\n"
            "    denominator = 0\n"
            "    return 1 / denominator\n"
            "nested()\n",
            encoding="utf-8",
        )
        sys.path.insert(0, temporary.name)
        self.addCleanup(sys.path.remove, temporary.name)
        self.addCleanup(sys.modules.pop, module_name, None)

        with sshscript.spy_imports():
            try:
                importlib.import_module(module_name)
            except ZeroDivisionError as exception:
                imported_exception = exception
            else:
                self.fail("imported .spy module did not raise")

        frame = self.spy_frames(path, imported_exception)[-1]
        self.assertEqual(frame.lineno, 3)
        self.assertEqual(frame.line, "return 1 / denominator")

    def test_dollar_command_behavior_still_executes(self):
        result = sshscript.run_script(
            "$true\ncommand_succeeded = ($.exitcode == 0)\n"
        )
        self.assertTrue(result["command_succeeded"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
