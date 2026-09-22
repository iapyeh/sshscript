"""Standard-library test entry point for the local dollar syntax suite."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parent.parent
RUNNER = SOURCE_ROOT / "sshscript.py"
SUITE = SOURCE_ROOT / "unittest" / "dollar_syntax.spy"
SUCCESS_MARKER = "All 9 credential-free dollar syntax tests passed."


class DollarSyntaxTests(unittest.TestCase):
    def test_dollar_syntax_suite_uses_only_localhost(self):
        with tempfile.TemporaryDirectory(
            prefix="sshscript-empty-home-"
        ) as empty_home:
            environment = os.environ.copy()
            environment["HOME"] = empty_home
            environment.pop("SSH_AUTH_SOCK", None)
            environment.pop("SSH_AGENT_PID", None)
            # Changing HOME also changes Python's user-site lookup. Preserve
            # the parent interpreter's import paths so normal SSHScript
            # dependencies remain available without restoring the real HOME.
            environment["PYTHONPATH"] = os.pathsep.join(
                path for path in sys.path if path
            )

            completed = subprocess.run(
                [sys.executable, str(RUNNER), str(SUITE)],
                cwd=SOURCE_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
            )

        diagnostic = (
            f"command: {sys.executable} {RUNNER} {SUITE}\n"
            f"exit code: {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
        self.assertEqual(completed.returncode, 0, diagnostic)
        self.assertIn(SUCCESS_MARKER, completed.stdout, diagnostic)
        self.assertEqual(completed.stdout.count("PASS:"), 9, diagnostic)


if __name__ == "__main__":
    unittest.main(verbosity=2)
