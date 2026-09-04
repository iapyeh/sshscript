"""Credential-free tests for SSHScript's regular Python module API.

These tests intentionally contain no SSHScript dollar syntax.  They exercise
the public API through local subprocesses only, so developers can run them
without SSH hosts, keys, usernames, or passwords.
"""

from concurrent.futures import ThreadPoolExecutor
import importlib
from pathlib import Path
import os
import shlex
import subprocess
import sys
import tempfile
import unittest

import sshscript
import patching


class ImportLayoutTests(unittest.TestCase):
    def test_import_does_not_modify_process_hooks(self):
        source_root = Path(__file__).resolve().parents[1]
        code = """
import __main__
import asyncio
import logging
import os
import sys
import threading
import warnings

thread_init = threading.Thread.__init__
thread_state = dict(threading.current_thread().__dict__)
meta_path = tuple(sys.meta_path)
warning_formatter = warnings.formatwarning
root_logger = logging.getLogger()
root_state = (root_logger.level, tuple(root_logger.handlers), tuple(root_logger.filters))
environment = dict(os.environ)
event_loop_policy = asyncio.get_event_loop_policy()
def verify_import():
    main_names = set(vars(__main__))
    import sshscript

    assert threading.Thread.__init__ is thread_init
    assert threading.current_thread().__dict__ == thread_state
    assert tuple(sys.meta_path) == meta_path
    assert warnings.formatwarning is warning_formatter
    assert (root_logger.level, tuple(root_logger.handlers), tuple(root_logger.filters)) == root_state
    assert os.environ == environment
    assert asyncio.get_event_loop_policy() is event_loop_policy
    assert set(vars(__main__)) == main_names

verify_import()
"""
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=source_root,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )

    def test_spy_imports_is_explicit_nested_and_reversible(self):
        with tempfile.TemporaryDirectory(
            prefix="sshscript-explicit-import-"
        ) as folder:
            module_name = "explicit_spy_module"
            Path(folder, f"{module_name}.spy").write_text(
                "answer = 42\n",
                encoding="utf-8",
            )
            original_meta_path = tuple(sys.meta_path)
            sys.path.insert(0, folder)
            self.addCleanup(sys.path.remove, folder)
            self.addCleanup(sys.modules.pop, module_name, None)

            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module(module_name)

            with sshscript.spy_imports():
                self.assertNotEqual(tuple(sys.meta_path), original_meta_path)
                with sshscript.spy_imports():
                    module = importlib.import_module(module_name)
                self.assertEqual(module.answer, 42)
                self.assertNotEqual(tuple(sys.meta_path), original_meta_path)

            self.assertEqual(tuple(sys.meta_path), original_meta_path)

            with self.assertRaisesRegex(RuntimeError, "context failed"):
                with sshscript.spy_imports():
                    raise RuntimeError("context failed")
            self.assertEqual(tuple(sys.meta_path), original_meta_path)

    def test_spy_imports_supports_packages_and_relative_imports(self):
        with tempfile.TemporaryDirectory(
            prefix="sshscript-explicit-package-"
        ) as folder:
            package_name = "explicit_spy_package"
            package = Path(folder, package_name)
            package.mkdir()
            Path(package, "__init__.spy").write_text(
                "from . import child\nanswer = child.answer\n",
                encoding="utf-8",
            )
            Path(package, "child.spy").write_text(
                "answer = 42\n",
                encoding="utf-8",
            )
            sys.path.insert(0, folder)
            self.addCleanup(sys.path.remove, folder)
            self.addCleanup(sys.modules.pop, package_name, None)
            self.addCleanup(sys.modules.pop, package_name + ".child", None)

            with sshscript.spy_imports():
                module = importlib.import_module(package_name)

            self.assertEqual(module.answer, 42)

    def test_flat_module_import_does_not_reenter_package_initializer(self):
        source_root = Path(__file__).resolve().parents[1]
        code = """
import sys
import sshscript

assert hasattr(sshscript, "run_file")
assert sshscript.sshscript_module is sshscript
assert "__init__" not in sys.modules
print(sshscript.__version__)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=source_root,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(result.stdout.strip(), sshscript.__version__)
        self.assertEqual(result.stderr, "")

    def test_package_import_uses_only_package_relative_modules(self):
        source_root = Path(__file__).resolve().parents[1]
        code = f"""
import importlib.util
import sys

source_root = {str(source_root)!r}
spec = importlib.util.spec_from_file_location(
    "sshscript",
    {str(source_root / "__init__.py")!r},
    submodule_search_locations=[source_root],
)
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)

assert hasattr(package, "run_file")
assert hasattr(package, "spy_imports")
assert package.run_file is package.sshscript.run_file
assert package.Session is package.session.Session
assert package.sshscript.sshscript_module is package
assert not any(
    name in sys.modules
    for name in (
        "channelgeneric",
        "channelssh",
        "channelsubprocess",
        "channelutils",
        "dollar",
        "dollarchanger",
        "dollarparser",
        "errorutils",
        "patching",
        "session",
        "sessionwrapper",
        "spyimporter",
        "stdio",
        "tokenparser",
    )
)
print(package.__version__)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=source_root.parent,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(result.stdout.strip(), sshscript.__version__)
        self.assertEqual(result.stderr, "")

    def test_cli_version_does_not_import_package_initializer(self):
        source_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(source_root / "sshscript.py"), "--version"],
            cwd=source_root,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(result.stdout.strip(), sshscript.__version__)
        self.assertEqual(result.stderr, "")


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

    def test_constructor_and_close_do_not_change_execution_stack(self):
        stack = patching.get_thread_stack()
        before = stack.snapshot()

        session = sshscript.Session()
        self.assertEqual(stack.snapshot(), before)
        session.close()
        self.assertEqual(stack.snapshot(), before)

    def test_run_and_context_manager_have_scoped_activation(self):
        stack = patching.get_thread_stack()
        before = stack.snapshot()
        session = sshscript.Session()

        namespace = session.run(
            "active_session = patching.peek_thread_stack()[-1]"
        )
        self.assertIs(namespace["active_session"], session)
        self.assertEqual(stack.snapshot(), before)

        with session:
            self.assertIs(stack[-1], session)
        self.assertEqual(stack.snapshot(), before)
        session.close()

    def test_direct_command_captures_output_and_exit_code(self):
        command = shlex.join(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "print('module-stdout'); "
                    "print('module-stderr', file=sys.stderr); "
                    "raise SystemExit(7)"
                ),
            ]
        )
        stdout, stderr = self.session.exec_command(
            command,
            shell=False,
            timeout=10,
        )

        self.assertEqual(str(stdout), "module-stdout\n")
        self.assertEqual(str(stderr), "module-stderr\n")
        self.assertEqual(self.session.exitcode, 7)
        self.assertFalse(self.session.dollar.use_shell)

    def test_call_alias_accepts_input_and_environment(self):
        command = shlex.join(
            [
                sys.executable,
                "-c",
                (
                    "import os, sys; "
                    "print(os.environ['SSHSCRIPT_MODULE_TEST']); "
                    "print(sys.stdin.read())"
                ),
            ]
        )
        stdout, stderr = self.session(
            command,
            shell=False,
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
            (TypeError, lambda: self.session.exec_command(["true"])),
            (TypeError, lambda: self.session.exec_command(("true",), shell=False)),
            (TypeError, lambda: self.session.exec_command([], shell=True)),
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

    def test_run_file_accepts_exactly_one_regular_file(self):
        with tempfile.TemporaryDirectory(
            prefix="sshscript-module-single-file-"
        ) as folder:
            folder_path = Path(folder)
            script = folder_path / "single.spy"
            marker = folder_path / "verified.txt"
            script.write_text(
                "from pathlib import Path\n"
                "assert seed == 40\n"
                "Path(marker_path).write_text('verified', encoding='utf-8')\n",
                encoding="utf-8",
            )

            exitcode = sshscript.run_file(
                script,
                vars={"seed": 40, "marker_path": str(marker)},
            )

            self.assertEqual(exitcode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "verified")

            with self.assertRaisesRegex(RuntimeError, "is not a file"):
                sshscript.run_file(folder_path)
            with self.assertRaisesRegex(TypeError, "script_path"):
                sshscript.run_file([script])
            with self.assertRaisesRegex(RuntimeError, "not found"):
                sshscript.run_file(str(folder_path / "*.spy"))

    def test_missing_script_has_a_clear_error(self):
        with tempfile.TemporaryDirectory(prefix="sshscript-module-missing-") as folder:
            missing = Path(folder) / "missing.spy"
            with self.assertRaisesRegex(RuntimeError, "missing[.]spy not found"):
                sshscript.run_file(str(missing))

    def test_cli_preserves_break_exit_status(self):
        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(
            prefix="sshscript-module-break-"
        ) as folder:
            script = Path(folder) / "break.spy"
            script.write_text("$.break(37)\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(source_root / "sshscript.py"), str(script)],
                cwd=source_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(completed.returncode, 37)


class ThreadedLocalModuleTests(unittest.TestCase):
    def test_independent_local_sessions_can_run_in_threads(self):
        def run_case(number):
            session = sshscript.Session()
            try:
                stdout, stderr = session.exec_command(
                    shlex.join(
                        [sys.executable, "-c", f"print('worker-{number}')"]
                    ),
                    shell=False,
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
