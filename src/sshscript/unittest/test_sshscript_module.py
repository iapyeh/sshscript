"""Credential-free tests for SSHScript's regular Python module API.

These tests intentionally contain no SSHScript dollar syntax.  They exercise
the public API through local subprocesses only, so developers can run them
without SSH hosts, keys, usernames, or passwords.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

import sshscript


class SessionModuleTests(unittest.TestCase):
    def setUp(self):
        self.session = sshscript.Session()

    def tearDown(self):
        self.session.close()

    def test_new_session_is_local_and_has_no_credentials(self):
        self.assertFalse(self.session.connected)
        self.assertIsNone(self.session.host)
        self.assertIsNone(self.session.username)
        self.assertIsNone(self.session.port)
        self.assertIs(self.session.local_session, self.session)

        with self.assertRaisesRegex(ValueError, "no execution result yet"):
            _ = self.session.stdout
        with self.assertRaisesRegex(ValueError, "no execution result yet"):
            _ = self.session.stderr
        with self.assertRaisesRegex(ValueError, "no execution result yet"):
            _ = self.session.exitcode

    def test_structured_command_captures_output_and_exit_code(self):
        stdout, stderr = self.session.exec_command(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "print('module-stdout'); "
                    "print('module-stderr', file=sys.stderr); "
                    "raise SystemExit(7)"
                ),
            ],
            timeout=10,
        )

        self.assertEqual(str(stdout), "module-stdout\n")
        self.assertEqual(str(stderr), "module-stderr\n")
        self.assertEqual(self.session.exitcode, 7)
        self.assertFalse(self.session.dollar.use_shell)

    def test_call_alias_accepts_input_and_environment(self):
        stdout, stderr = self.session(
            [
                sys.executable,
                "-c",
                (
                    "import os, sys; "
                    "print(os.environ['SSHSCRIPT_MODULE_TEST']); "
                    "print(sys.stdin.read())"
                ),
            ],
            input="input-from-test",
            env={"SSHSCRIPT_MODULE_TEST": "environment-from-test"},
            timeout=10,
        )

        self.assertEqual(
            str(stdout),
            "environment-from-test\ninput-from-test\n",
        )
        self.assertEqual(str(stderr), "")
        self.assertEqual(self.session.exitcode, 0)

    def test_automatic_and_explicit_shell_selection(self):
        stdout, stderr = self.session.exec_command(
            "printf 'module-api' | tr a-z A-Z",
            timeout=10,
        )

        self.assertEqual(str(stdout), "MODULE-API")
        self.assertEqual(str(stderr), "")
        self.assertEqual(self.session.exitcode, 0)
        self.assertTrue(self.session.dollar.use_shell)
        self.assertIn("pipeline", self.session.dollar.shell_reasons)

        stdout, stderr = self.session.exec_command(
            "printf 'forced-shell'",
            shell=True,
            timeout=10,
        )
        self.assertEqual(str(stdout), "forced-shell")
        self.assertEqual(str(stderr), "")
        self.assertTrue(self.session.dollar.use_shell)

    def test_command_validation_fails_before_starting_a_process(self):
        invalid_calls = (
            (TypeError, lambda: self.session.exec_command(None)),
            (ValueError, lambda: self.session.exec_command("   ")),
            (ValueError, lambda: self.session.exec_command([], shell=True)),
            (TypeError, lambda: self.session.exec_command("true", shell=1)),
            (
                ValueError,
                lambda: self.session.exec_command(
                    "true", shell="bash", shell_executable="sh"
                ),
            ),
        )

        for exception_type, call in invalid_calls:
            with self.subTest(exception_type=exception_type.__name__):
                with self.assertRaises(exception_type):
                    call()

    def test_close_is_idempotent(self):
        self.session.close()
        self.session.close()
        self.assertTrue(self.session.closed)


class ScriptRunnerModuleTests(unittest.TestCase):
    def test_run_script_executes_regular_python_and_returns_namespace(self):
        namespace = sshscript.run_script(
            "answer = seed + 2",
            {"seed": 40},
        )

        self.assertEqual(namespace["answer"], 42)

    def test_run_file_shares_explicit_exports_between_sorted_files(self):
        with tempfile.TemporaryDirectory(prefix="sshscript-module-test-") as folder:
            folder_path = Path(folder)
            marker = folder_path / "verified.txt"
            (folder_path / "01_export.spy").write_text(
                "shared_value = seed + 2\n"
                "__export__ = ['shared_value']\n",
                encoding="utf-8",
            )
            (folder_path / "02_verify.spy").write_text(
                "from pathlib import Path\n"
                "assert shared_value == 42\n"
                "Path(marker_path).write_text('verified', encoding='utf-8')\n",
                encoding="utf-8",
            )

            exitcode = sshscript.run_file(
                folder,
                vars={"seed": 40, "marker_path": str(marker)},
            )

            self.assertEqual(exitcode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "verified")

    def test_run_file_reports_sorted_order_without_execution(self):
        with tempfile.TemporaryDirectory(prefix="sshscript-module-order-") as folder:
            folder_path = Path(folder)
            later = folder_path / "20_later.spy"
            earlier = folder_path / "10_earlier.spy"
            later.write_text("raise AssertionError('must not run')\n", encoding="utf-8")
            earlier.write_text("raise AssertionError('must not run')\n", encoding="utf-8")

            output = StringIO()
            with redirect_stdout(output):
                exitcode = sshscript.run_file(folder, showRunOrder=True)

            self.assertEqual(exitcode, 0)
            self.assertEqual(
                output.getvalue().splitlines(),
                [str(earlier.absolute()), str(later.absolute())],
            )

    def test_missing_script_has_a_clear_error(self):
        with tempfile.TemporaryDirectory(prefix="sshscript-module-missing-") as folder:
            missing = Path(folder) / "missing.spy"
            with self.assertRaisesRegex(RuntimeError, "missing[.]spy not found"):
                sshscript.run_file(str(missing))


class ThreadedLocalModuleTests(unittest.TestCase):
    def test_independent_local_sessions_can_run_in_threads(self):
        def run_case(number):
            session = sshscript.Session()
            try:
                stdout, stderr = session.exec_command(
                    [sys.executable, "-c", f"print('worker-{number}')"],
                    timeout=10,
                )
                return str(stdout).strip(), str(stderr), session.exitcode
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(run_case, range(3)))

        self.assertEqual(
            results,
            [
                ("worker-0", "", 0),
                ("worker-1", "", 0),
                ("worker-2", "", 0),
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
