"""Run the same credential-free gates in development and release layouts."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
source = root / 'src/sshscript' if (root / 'src/sshscript').is_dir() else root
env = os.environ.copy()
env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
commands = [
    ['-m', 'compileall', '-q', '-x', 'unittest-v3', str(source)],
    ['-m', 'unittest', 'discover', '-v', '-s', 'unittest', '-p', 'test_*.py'],
    ['-O', '-m', 'unittest', 'discover', '-v', '-s', 'unittest', '-p', 'test_*.py'],
    ['sshscript.py', 'unittest/dollar_syntax.spy'],
    ['unittest/check_package_asserts.py'],
]
for command in commands:
    subprocess.run([sys.executable, *command], cwd=source, env=env, check=True)
