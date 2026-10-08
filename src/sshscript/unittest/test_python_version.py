"""Startup guards must reject old interpreters before feature imports."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT.parent / '_sshscript_cli.py' if ROOT.name == 'sshscript' else ROOT / '_sshscript_cli.py'


class PythonVersionTests(unittest.TestCase):
    def run_probe(self, body, version=(3, 10, 14)):
        code = """
import importlib.util
import runpy
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, %r)
sys.version_info = %r
sys.executable = '/test/python'
""" % (str(ROOT), version)
        return subprocess.run(
            [sys.executable, '-c', code + body],
            cwd=ROOT, capture_output=True, text=True,
        )

    def assert_rejected_cli(self, result):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr,
                         'SSHScript requires Python 3.11 or newer.\n'
                         'Detected Python 3.10.14 at /test/python.\n')

    def test_direct_script_rejects_before_feature_imports(self):
        self.assert_rejected_cli(self.run_probe(
            "try:\n"
            "    runpy.run_path(%r, run_name='__main__')\n"
            "finally:\n"
            "    assert 'session' not in sys.modules\n"
            "    assert 'paramiko' not in sys.modules\n" % str(ROOT / 'sshscript.py')
        ))

    def test_console_bootstrap_rejects_before_package_import(self):
        self.assert_rejected_cli(self.run_probe(
            "try:\n"
            "    runpy.run_path(%r, run_name='__main__')\n"
            "finally:\n"
            "    assert 'sshscript' not in sys.modules\n"
            "    assert 'paramiko' not in sys.modules\n" % str(BOOTSTRAP)
        ))

    def test_api_imports_raise_importerror_before_feature_imports(self):
        for package in (False, True):
            with self.subTest(package=package):
                filename = ROOT / ('__init__.py' if package else 'sshscript.py')
                body = r"""
spec = importlib.util.spec_from_file_location('sshscript', %r%s)
module = importlib.util.module_from_spec(spec)
sys.modules['sshscript'] = module
try:
    spec.loader.exec_module(module)
except ImportError as exc:
    assert str(exc) == ('SSHScript requires Python 3.11 or newer.\n'
                        'Detected Python 3.10.14 at /test/python.')
else:
    raise AssertionError('Unsupported interpreter was accepted')
assert 'paramiko' not in sys.modules
assert 'session' not in sys.modules
assert 'sshscript.session' not in sys.modules
assert 'sshscript.sshscript' not in sys.modules
""" % (str(filename), ', submodule_search_locations=[%r]' % str(ROOT) if package else '')
                result = self.run_probe(body)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_boundary(self):
        for version in ((3, 6, 0), (3, 9, 20), (3, 10, 99), (3, 11, 0), (3, 14, 0)):
            with self.subTest(version=version):
                result = self.run_probe("""
from _runtime import require_python
try:
    require_python()
except ImportError:
    assert sys.version_info < (3, 11)
else:
    assert sys.version_info >= (3, 11)
""", version)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_supported_console_bootstrap_calls_cli(self):
        result = self.run_probe("""
import types
package = types.ModuleType('sshscript')
package.__path__ = []
cli = types.ModuleType('sshscript.sshscript')
cli.main = lambda: 42
sys.modules['sshscript'] = package
sys.modules['sshscript.sshscript'] = cli
bootstrap = runpy.run_path(%r)
assert bootstrap['main']() == 42
""" % str(BOOTSTRAP), (3, 11, 0))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_startup_sources_parse_with_python36_grammar(self):
        for path in (ROOT / '__init__.py', ROOT / 'sshscript.py',
                     ROOT / '_runtime.py', BOOTSTRAP):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(), feature_version=(3, 6))


if __name__ == '__main__':
    unittest.main()
