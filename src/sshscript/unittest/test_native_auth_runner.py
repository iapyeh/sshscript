"""Offline safeguards for the privileged native-auth evidence runner."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'tools/run_native_auth_ci.py').is_file())
spec = importlib.util.spec_from_file_location('native_auth_runner', ROOT / 'tools/run_native_auth_ci.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class NativeRunnerTests(unittest.TestCase):
    def test_normal_discovery_never_runs_native_authentication(self):
        path = ROOT / ('src/sshscript' if (ROOT / 'src/sshscript').is_dir() else '') / 'unittest/test_native_console_authentication.py'
        spec = importlib.util.spec_from_file_location('native_suite_offline', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, 'Session', side_effect=AssertionError('native session must not be created')):
            result = unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromTestCase(module.NativeAuthenticationTests).run(result)
        self.assertEqual(result.testsRun, 8)
        self.assertEqual(len(result.skipped), 8)
        self.assertFalse(result.errors or result.failures)

    def run_fixture(self, local_report=None, timeout=False):
        with tempfile.TemporaryDirectory(prefix='sshscript-native-runner-test-') as folder:
            root = Path(folder)
            wheel, output = root / 'candidate.whl', root / 'evidence.json'
            wheel.write_bytes(b'candidate artifact')
            environment = {'SSHSCRIPT_OPENSSH_TESTS': '1'}
            values = dict(USER='throwaway-user', PASSWORD='secret-one', TARGET_USER='throwaway-target',
                          TARGET_PASSWORD='secret-two', HOST='127.0.0.1', PORT='22222', KEY='/fixture/key', HOME='/fixture/home')
            environment.update({'SSHSCRIPT_OPENSSH_' + name: value for name, value in values.items()})
            calls = []
            def run(command, **kwargs):
                if 'input' not in kwargs:
                    return subprocess.CompletedProcess(command, 0, '', '')
                config = json.loads(kwargs['input'])
                calls.append((command, config))
                if timeout and config['backend'] == 'local':
                    raise subprocess.TimeoutExpired(command, 240)
                report = local_report if config['backend'] == 'local' and local_report is not None else dict(
                    backend=config['backend'], passed=True, tests=8, skipped=0)
                return subprocess.CompletedProcess(command, 0, 'NATIVE_AUTH_REPORT=' + json.dumps(report) + '\n',
                                                   'diagnostic secret-one secret-two\n')
            capture = StringIO()
            with patch.object(sys, 'argv', ['run_native_auth_ci.py', '--wheel', str(wheel), '--report', str(output)]), \
                 patch.object(runner.sys, 'platform', 'linux'), patch.dict(runner.os.environ, environment, clear=True), \
                 patch.object(runner.venv.EnvBuilder, 'create'), patch.object(runner.subprocess, 'run', side_effect=run), \
                 patch.object(runner.subprocess, 'check_output', return_value='1234\n'), redirect_stdout(capture):
                status = runner.main()
            evidence = json.loads(output.read_text())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            for secret in ('secret-one', 'secret-two'):
                self.assertNotIn(secret, capture.getvalue())
                self.assertNotIn(secret, output.read_text())
                self.assertTrue(all(secret not in ' '.join(command) for command, _ in calls))
            self.assertEqual(len(evidence['wheel_sha256']), 64)
            self.assertEqual([config['backend'] for _, config in calls], ['local', 'ssh'])
            self.assertEqual(calls[0][0][:4], ['sudo', '-n', '-H', '-u'])
            self.assertNotEqual(calls[1][0][0], 'sudo')
            self.assertTrue(all('-I' in command for command, _ in calls))
            return status, evidence

    def test_both_backends_artifact_identity_and_secret_handling(self):
        status, evidence = self.run_fixture()
        self.assertEqual(status, 0)
        self.assertTrue(evidence['passed'])

    def test_skipped_or_empty_native_evidence_cannot_pass(self):
        for report in (dict(passed=True, tests=8, skipped=1), dict(passed=True, tests=0, skipped=0)):
            with self.subTest(report=report):
                status, evidence = self.run_fixture(local_report=report)
                self.assertEqual(status, 1)
                self.assertFalse(evidence['passed'])

    def test_timeout_is_saved_as_unresolved_and_other_backend_still_runs(self):
        status, evidence = self.run_fixture(timeout=True)
        self.assertEqual(status, 1)
        self.assertFalse(evidence['passed'])
        self.assertIn('unresolved', evidence['reports'][0]['error'])
        self.assertTrue(evidence['reports'][1]['passed'])


if __name__ == '__main__':
    unittest.main()
