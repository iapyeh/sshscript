"""Check PEP 561 consumer behavior using real positive and negative examples."""
from pathlib import Path
import shutil
import re
import subprocess
import sys
import tempfile

VALID = '''from typing import assert_type, Literal
from pathlib import Path
from paramiko import MissingHostKeyPolicy, AutoAddPolicy
from sshscript import Session, CommandResult, JobResult, CommandJob, Console, ConsoleUpdate, SwitchCredentials
s = Session()
s.set(check=True, log_level="DEBUG")
s.verbose = False
s.log_level = "WARNING"
s.set(missing_host_key_policy=AutoAddPolicy())
s.set(known_hosts_source="chain", known_hosts_path=Path("/trust/known_hosts"))
s.known_hosts_source = "parent"
s.known_hosts_path = None
assert_type(s.get("known_hosts_source"), Literal["local", "parent", "chain"])
assert_type(s.get("known_hosts_path"), str | None)
s.missing_host_key_policy = AutoAddPolicy
s.missing_host_key_policy = None
assert_type(s.get("missing_host_key_policy"), MissingHostKeyPolicy | type[MissingHostKeyPolicy] | None)
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
with Console(s, credential_resolver=lambda request: SwitchCredentials(None)) as embedded:
    assert_type(embedded.submit('x=42'), ConsoleUpdate)
    assert_type(embedded.poll().stdout, str)
    assert_type(embedded.connection, Session)
    assert_type(embedded.environments[0].effective_user, str)
    embedded.enter("python3 -q", prompt=">>>")
    assert_type(embedded.input(secret=True), None)
    assert_type(embedded.input("reply"), str | None)
    assert_type(embedded.exit("quit()"), None)
with s.connect(hostname="host", known_hosts_source="local", parent_key_filename=Path("/key"), passphrase="fixture", proxy_command=None, proxy_jump=None, timeout=3, allow_agent=False) as remote:
    assert_type(remote, Session)
'''
INVALID = '''from sshscript import Session
s = Session()
s.set(chek=True)
s.verbose = "yes"
s.exec_command(123)
s.exec_command(["true"], check="yes")
s.set(known_hosts_source="typo")
s.set(known_hosts_path=123)
s.connect("host", known_hosts_source="typo")
s.connect("host", key_path="/key")
s.connect("host", pkey_path="/key")
s.connect("host", proxyCommand="unused")
s.connect("host", known_hosts="local")
s.connect("host", policy=None)
s.connect("host", "user")
from sshscript import Console
c = Console(s)
c.input(secret="yes")
c.input("plaintext", secret=True)
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
            if name == 'invalid':
                expected = {index for index, line in enumerate(INVALID.splitlines(), 1)
                            if line.startswith(('s.', 'c.input'))}
                rejected = {int(line) for line in re.findall(r'invalid\.py:(\d+): error:', output)}
                if result.returncode != 1 or not expected <= rejected:
                    raise RuntimeError('Expected every invalid use to be rejected:\n' + output)
        print('Public types: valid consumer accepted; fifteen invalid uses rejected')

if __name__ == '__main__':
    main()
