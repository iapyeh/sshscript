"""Check PEP 561 consumer behavior using real positive and negative examples."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

VALID = '''from typing import assert_type
from paramiko import MissingHostKeyPolicy, AutoAddPolicy
from sshscript import Session, CommandResult, JobResult, CommandJob
s = Session()
s.set(check=True, log_level="DEBUG")
s.verbose = False
s.log_level = "WARNING"
s.set(policy=AutoAddPolicy())
s.policy = AutoAddPolicy
s.policy = None
assert_type(s.get("policy"), MissingHostKeyPolicy | type[MissingHostKeyPolicy] | None)
assert_type(s.get("check"), bool)
assert_type(s.get("log_level"), int)
r = s.exec_command(["printf", "ready"], check=True)
assert_type(r, CommandResult[int])
assert_type(r.stdout, str)
assert_type(r.exitcode, int)
m = s.exec_command(["printf", "ready"], command_timeout=2)
assert_type(m, JobResult)
assert_type(m.exitcode, int | None)
assert_type(s(["true"], command_timeout=2), JobResult)
assert_type(s.start(["true"]), CommandJob)
with s.shell() as console:
    assert_type(console.start("printf ready", timeout=3), CommandJob)
    assert_type(console.send("partial"), None)
    assert_type(console.input("reply", timeout=3), str | None)
    shell_result = console("printf ready", check=True)
    if isinstance(shell_result, CommandResult):
        assert_type(shell_result, CommandResult[int])
        assert_type(shell_result.stdout, str)
with s.connect("host") as remote:
    assert_type(remote, Session)
'''
INVALID = '''from sshscript import Session
s = Session()
s.set(chek=True)
s.verbose = "yes"
s.exec_command(123)
s.exec_command(["true"], check="yes")
'''

def main():
    root = Path(__file__).resolve().parents[1]
    package = root / 'src/sshscript' if (root / 'src/sshscript').is_dir() else root
    with tempfile.TemporaryDirectory(prefix='sshscript-types-') as tmp:
        folder = Path(tmp)
        target = folder / 'sshscript'
        target.mkdir()
        for pattern in ('*.py', '*.pyi', 'py.typed'):
            for source in package.glob(pattern):
                shutil.copy2(source, target / source.name)
        for name, source in [('valid', VALID), ('invalid', INVALID)]:
            path = folder / f'{name}.py'
            path.write_text(source)
            result = subprocess.run(
                [sys.executable, '-m', 'mypy', '--strict', '--ignore-missing-imports',
                 '--follow-imports=silent', '--cache-dir', str(folder / 'cache'), str(path)],
                cwd=folder, text=True, capture_output=True, timeout=60,
            )
            output = result.stdout + result.stderr
            if name == 'valid' and result.returncode:
                raise RuntimeError(output)
            if name == 'invalid' and (result.returncode != 1 or 'Found 4 errors' not in output):
                raise RuntimeError('Expected all four invalid uses to be rejected:\n' + output)
        print('Public types: valid consumer accepted; four invalid uses rejected')

if __name__ == '__main__':
    main()
