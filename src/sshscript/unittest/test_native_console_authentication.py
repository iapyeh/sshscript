"""Opt-in native su/sudo contracts; ordinary discovery never uses host credentials.

Run through tools/run_native_auth_ci.py on a disposable Linux runner. The CLI
accepts fixture configuration through stdin, never password command arguments.
"""
import json
import os
import platform
import shlex
import subprocess
import sys
import time
import unittest

from sshscript import Session

CONFIG = None


@unittest.skipUnless(CONFIG is not None, "native authentication requires an explicit disposable fixture")
class NativeAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.parent = Session()
        self.addCleanup(self.parent.close)
        if CONFIG['backend'] == 'ssh':
            self.session = self.parent.connect(
                CONFIG['host'], username=CONFIG['user'], port=CONFIG['port'],
                key_filename=CONFIG['key'], ssh_config=False,
                look_for_keys=False, allow_agent=False,
                timeout=5, banner_timeout=5, auth_timeout=5,
            )
        else:
            self.session = self.parent
        self.original_uid = self.session(['id', '-u'], check=True).stdout.strip()
        self.assertEqual(self.original_uid, CONFIG['uid'])
        self.assertNotEqual(self.original_uid, '0', 'fixture must exercise real non-root authentication')
        self.target_uid = self.session(['id', '-u', CONFIG['target_user']], check=True).stdout.strip()
        self.assertNotEqual(self.target_uid, self.original_uid)
        self.session.set(verbose=False, verbose_stderr=False, check=True)

    def identity(self, console):
        result = console('printf "%s:%s\\n" "$(id -u)" "$$"', check=True, command_timeout=5)
        value = result.stdout.strip().splitlines()[-1]
        uid, pid = value.split(':')
        self.assertTrue(uid.isdigit() and pid.isdigit())
        return uid, pid

    def assert_recovery(self, shell, before, *, required):
        try:
            after = self.identity(shell)
        except RuntimeError as error:
            if required:
                raise
            self.assertIn('recovery is unconfirmed', str(error))
            CONFIG['outcomes'].append({'case': self._testMethodName, 'recovery': 'unconfirmed_channel_rejected'})
        else:
            self.assertEqual(after, before, 'parent UID and shell PID must both survive')
            CONFIG['outcomes'].append({'case': self._testMethodName, 'recovery': 'confirmed'})

    def test_real_success_option_matrix(self):
        for kind in ('su', 'sudo'):
            for login in (False, True):
                for pty in (False, True):
                    for base_shell in (False, True):
                        with self.subTest(kind=kind, login=login, pty=pty, shell=base_shell):
                            options = dict(login=login, get_pty=pty, shell=base_shell, enter_timeout=15)
                            context = (self.session.su(CONFIG['target_user'], CONFIG['target_password'], **options)
                                       if kind == 'su' else self.session.sudo(CONFIG['password'], **options))
                            with context as target:
                                self.assertEqual(self.identity(target)[0], self.target_uid if kind == 'su' else '0')
                            self.assertEqual(self.session(['id', '-u'], check=True).stdout.strip(), self.original_uid)

    def test_nested_success_restores_parent_uid_and_pid(self):
        with self.session.shell('bash', get_pty=True) as shell:
            before = self.identity(shell)
            with shell.su(CONFIG['target_user'], CONFIG['target_password'], enter_timeout=15) as target:
                self.assertEqual(self.identity(target)[0], self.target_uid)
            self.assertEqual(self.identity(shell), before)
            with shell.sudo(CONFIG['password'], enter_timeout=15) as target:
                self.assertEqual(self.identity(target)[0], '0')
            self.assertEqual(self.identity(shell), before)
            # The retained sudo-to-su route must actually enter the non-root target.
            with shell.sudo(CONFIG['password'], username=CONFIG['target_user'], enter_timeout=15) as target:
                self.assertEqual(self.identity(target)[0], self.target_uid)
            self.assertEqual(self.identity(shell), before)

    def test_wrong_password_never_enters_body(self):
        for kind in ('su', 'sudo'):
            with self.subTest(kind=kind), self.session.shell('bash', get_pty=True) as shell:
                before = self.identity(shell)
                wrong = 'invalid-' + CONFIG['password']
                context = (shell.su(CONFIG['target_user'], wrong, enter_timeout=15)
                           if kind == 'su' else shell.sudo(wrong, enter_timeout=15))
                entered = False
                with self.assertRaises(PermissionError):
                    with context:
                        entered = True
                self.assertFalse(entered)
                self.assert_recovery(shell, before, required=False)

    def test_missing_password_never_enters_body(self):
        for kind in ('su', 'sudo'):
            with self.subTest(kind=kind), self.session.shell('bash', get_pty=True) as shell:
                before = self.identity(shell)
                context = (shell.su(CONFIG['target_user'], password=None, enter_timeout=15)
                           if kind == 'su' else shell.sudo(password=None, enter_timeout=15))
                entered = False
                with self.assertRaises(PermissionError):
                    with context:
                        entered = True
                self.assertFalse(entered)
                self.assert_recovery(shell, before, required=False)

    def test_real_sudoers_denial_restores_parent(self):
        with self.session.shell('bash', get_pty=True) as shell:
            before = self.identity(shell)
            entered = False
            # Fixture policy specifically denies /usr/bin/false, for all arguments.
            with self.assertRaises((PermissionError, RuntimeError)):
                with shell.sudo(CONFIG['password'], command='sudo -k -S /usr/bin/false {auth_command}', enter_timeout=15):
                    entered = True
            self.assertFalse(entered)
            self.assert_recovery(shell, before, required=True)

    def test_real_passwordless_sudo(self):
        with self.session.shell('bash', get_pty=True) as shell:
            before = self.identity(shell)
            command = 'sudo -k -n -u ' + shlex.quote(CONFIG['target_user']) + ' {auth_command}'
            for password in (None, CONFIG['password']):
                with shell.sudo(password=password, username=CONFIG['target_user'], command=command, enter_timeout=15) as target:
                    self.assertEqual(self.identity(target)[0], self.target_uid)
                self.assertEqual(self.identity(shell), before)

    def test_short_authentication_deadline_never_enters_body(self):
        for kind in ('su', 'sudo'):
            with self.subTest(kind=kind), self.session.shell('bash', get_pty=True) as shell:
                before = self.identity(shell)
                options = dict(enter_timeout=0.5)
                wrong = 'invalid-' + CONFIG['password']
                context = (shell.su(CONFIG['target_user'], wrong, **options)
                           if kind == 'su' else shell.sudo(wrong, **options))
                entered = False
                started = time.monotonic()
                with self.assertRaises((TimeoutError, PermissionError, RuntimeError)) as caught:
                    with context:
                        entered = True
                self.assertFalse(entered)
                self.assertLess(time.monotonic() - started, 3.5)
                # A host may reject before the deadline, or remain unresolved.
                # Record which occurred instead of assuming a PAM delay.
                CONFIG['outcomes'].append(dict(case=self._testMethodName, kind=kind,
                                                failure=type(caught.exception).__name__))
                self.assert_recovery(shell, before, required=False)

    def test_deadline_never_enters_body_and_exposes_recovery(self):
        for kind in ('su', 'sudo'):
            with self.subTest(kind=kind), self.session.shell('bash', get_pty=True) as shell:
                before = self.identity(shell)
                options = dict(initials=['sleep 5'], enter_timeout=1)
                context = (shell.su(CONFIG['target_user'], CONFIG['target_password'], **options)
                           if kind == 'su' else shell.sudo(CONFIG['password'], **options))
                entered = False
                started = time.monotonic()
                with self.assertRaises(TimeoutError):
                    with context:
                        entered = True
                self.assertFalse(entered)
                self.assertLess(time.monotonic() - started, 5)
                self.assert_recovery(shell, before, required=False)


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.cases.append(dict(case=test.id(), status='passed'))

    def addError(self, test, err):
        super().addError(test, err)
        self.cases.append(dict(case=test.id(), status='error', exception=err[0].__name__))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.cases.append(dict(case=test.id(), status='failed', exception=err[0].__name__))

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        self.cases.append(dict(case=subtest.id(), status='passed' if err is None else 'failed',
                               exception=None if err is None else err[0].__name__))


def metadata():
    tools = {}
    for name in ('su', 'sudo', 'bash'):
        probe = subprocess.run([name, '--version'], text=True, capture_output=True, timeout=5)
        tools[name] = (probe.stdout + probe.stderr).splitlines()[:2]
    return dict(platform=platform.platform(), python=platform.python_version(),
                package_version=__import__('sshscript').__version__, tools=tools,
                backend=CONFIG['backend'], uid=CONFIG['uid'], target_shell='bash',
                outcomes=CONFIG['outcomes'])


def main():
    global CONFIG
    if sys.argv[1:] != ['--fixture-stdin']:
        raise SystemExit('usage: test_native_console_authentication.py --fixture-stdin (disposable fixture JSON on stdin)')
    CONFIG = json.load(sys.stdin)
    if CONFIG.get('disposable_fixture') is not True or CONFIG.get('backend') not in ('local', 'ssh'):
        raise SystemExit('an explicit disposable local or SSH fixture is required')
    CONFIG['outcomes'] = []
    if CONFIG['backend'] == 'ssh':
        os.environ['HOME'] = CONFIG['home']
    NativeAuthenticationTests.__unittest_skip__ = False
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeAuthenticationTests)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = metadata()
    report.update(cases=result.cases, tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  skipped=len(result.skipped), passed=result.wasSuccessful() and not result.skipped)
    print('NATIVE_AUTH_REPORT=' + json.dumps(report, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
