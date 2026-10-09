"""Run the same credential-free gates in development and release layouts."""
import os
from pathlib import Path
import subprocess
import sys
from prepare_release import TESTS, validate_release_inputs

root = Path(__file__).resolve().parents[1]
source = root / 'src/sshscript' if (root / 'src/sshscript').is_dir() else root
validate_release_inputs(root)
if (root / '.git').exists():
    prefix = source.relative_to(root)
    tracked = subprocess.check_output(
        ['git', 'ls-files', '-z', '--', str(prefix / 'unittest'),
         str(prefix / 'unittest-v3')], cwd=root,
    ).decode().split('\0')
    allowed = {str(prefix / 'unittest' / name) for name in TESTS}
    unexpected = sorted(path for path in tracked if path and path not in allowed)
    if unexpected:
        raise SystemExit('Private or unapproved test files are tracked:\n' +
                         '\n'.join(unexpected))
env = os.environ.copy()
# A user-bin symlink can sit beside a different 'python3'. Resolve it for
# system interpreters, but retain a venv's bin so child commands use its deps.
interpreter_bin = (Path(sys.executable).parent if sys.prefix != sys.base_prefix
                   else Path(sys.executable).resolve().parent)
env['PATH'] = str(interpreter_bin) + os.pathsep + env.get('PATH', '')
commands = [
    ['-m', 'compileall', '-q', '-x', 'unittest-v3', str(source)],
    ['-m', 'unittest', 'discover', '-v', '-s', 'unittest', '-p', 'test_*.py'],
    ['-O', '-m', 'unittest', 'discover', '-v', '-s', 'unittest', '-p', 'test_*.py'],
    ['sshscript.py', 'unittest/dollar_syntax.spy'],
    ['unittest/check_package_asserts.py'],
]
for command in commands:
    subprocess.run([sys.executable, *command], cwd=source, env=env, check=True)
