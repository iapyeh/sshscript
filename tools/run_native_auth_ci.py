"""Run the installed wheel's native auth tests on a disposable Linux CI host.

No accounts or sudoers changes are made here. setup_openssh_ci.sh owns that
fixture. Secrets are passed through stdin and redacted before diagnostics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or os.environ.get('SSHSCRIPT_OPENSSH_TESTS') != '1':
        parser.error('requires the disposable Linux setup_openssh_ci.sh fixture')
    source = Path(__file__).resolve().parents[1]
    package = source / 'src/sshscript' if (source / 'src/sshscript').is_dir() else source
    names = dict(user='USER', password='PASSWORD', target_user='TARGET_USER', target_password='TARGET_PASSWORD',
                 host='HOST', port='PORT', key='KEY', home='HOME')
    config = {key: os.environ['SSHSCRIPT_OPENSSH_' + suffix] for key, suffix in names.items()}
    config['port'] = int(config['port'])
    config['uid'] = subprocess.check_output(['id', '-u', config['user']], text=True).strip()
    config['disposable_fixture'] = True
    reports = []
    failed = False
    wheel = args.wheel.resolve()
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='sshscript-native-auth-', dir='/tmp') as tmp:
        root = Path(tmp)
        # The throwaway non-root fixture user must traverse this directory.
        # Passwords/keys are never stored here; installed code is read-only to it.
        root.chmod(0o755)
        venv.EnvBuilder(with_pip=True, symlinks=True).create(root / 'venv')
        python = root / 'venv/bin/python'
        subprocess.run([str(python), '-m', 'pip', 'install', str(args.wheel.resolve())], check=True)
        test = root / 'test_native_console_authentication.py'
        shutil.copyfile(package / 'unittest' / test.name, test)
        test.chmod(0o644)
        for backend in ('local', 'ssh'):
            config['backend'] = backend
            command = [str(python), '-B', '-I', str(test), '--fixture-stdin']
            if backend == 'local':
                command = ['sudo', '-n', '-H', '-u', config['user'], '--', *command]
            try:
                result = subprocess.run(command, input=json.dumps(config), text=True, capture_output=True, timeout=240)
            except subprocess.TimeoutExpired:
                failed = True
                reports.append(dict(backend=backend, passed=False, error='native runner exceeded 240 seconds; state unresolved'))
                continue
            diagnostic = result.stdout + result.stderr
            for secret in (config['password'], config['target_password']):
                diagnostic = diagnostic.replace(secret, '[redacted]')
            print(diagnostic, end='')
            lines = [line for line in result.stdout.splitlines() if line.startswith('NATIVE_AUTH_REPORT=')]
            if len(lines) != 1:
                failed = True
                reports.append(dict(backend=backend, passed=False, error='native runner did not return evidence'))
            else:
                report = json.loads(lines[0].split('=', 1)[1])
                reports.append(report)
                failed |= (result.returncode != 0 or report.get('passed') is not True
                           or report.get('tests', 0) < 9 or report.get('skipped') != 0)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(schema_version=1, wheel=wheel.name, wheel_sha256=digest, reports=reports, passed=not failed), indent=2) + '\n')
    args.report.chmod(0o600)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
