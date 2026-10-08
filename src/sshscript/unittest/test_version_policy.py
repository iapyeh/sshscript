"""Version identity, production boundaries and executable upgrade guidance."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
import subprocess
import sys
import unittest
from packaging.version import Version
import sshscript
from _version import __version__

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'tools/version_policy.py').is_file())
sys.path.insert(0, str(ROOT / 'tools'))
from version_policy import require_production_version


class VersionPolicyTests(unittest.TestCase):
    def test_runtime_cli_and_development_documentation_agree(self):
        self.assertEqual(sshscript.__version__, __version__)
        source = ROOT / 'src/sshscript' if (ROOT / 'src/sshscript').is_dir() else ROOT
        result = subprocess.run([sys.executable, str(source / 'sshscript.py'), '--version'],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), __version__)
        self.assertIn(__version__, (ROOT / 'API_GUIDE.md').read_text())
        self.assertIn(__version__, (ROOT / 'VERSIONING.md').read_text())
        if Version(__version__).is_prerelease:
            self.assertNotIn('Development Status :: 5 - Production/Stable',
                             (ROOT / 'pyproject.toml').read_text())

    def test_production_rejects_development_candidates_and_local_versions(self):
        for value in ('4.0.0.dev0', '4.0.0a1', '4.0.0b1', '4.0.0rc1', '4.0.0+private'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'not a production version'):
                require_production_version(value)
        self.assertEqual(str(require_production_version('4.0.0')), '4.0.0')

    def test_migration_example_retains_completed_console_result(self):
        text = (ROOT / 'VERSIONING.md').read_text()
        examples = re.findall(r'<!-- migration-example -->\n```python\n(.*?)```', text, re.S)
        self.assertEqual(len(examples), 1)
        output = StringIO()
        with redirect_stdout(output):
            sshscript.run_script(examples[0])
        self.assertEqual(output.getvalue(), 'first 0\n')


if __name__ == '__main__':
    unittest.main()
