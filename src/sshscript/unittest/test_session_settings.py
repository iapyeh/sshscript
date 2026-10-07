"""Session policy precedence, isolation and CLI/script integration."""
from contextlib import redirect_stdout
from io import StringIO
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from session import Session
from sessionsettings import execution_defaults
import errorutils
import sshscript


class SettingsTests(unittest.TestCase):
    def session(self, parent=None):
        session = Session(parent)
        self.addCleanup(session.close)
        return session

    def test_validation_properties_and_child_snapshot(self):
        parent = self.session()
        parent.set(check=True, verbose=True, log_level='DEBUG')
        child = self.session(parent)
        parent.set(check=False, verbose=False)
        self.assertTrue(child.check)
        child.verbose = False
        self.assertFalse(child.get('verbose'))
        before = child.get()
        with self.assertRaises(TypeError):
            child.set(check=False, verbose=1)
        self.assertEqual(child.get(), before)
        with self.assertRaises(ValueError): child.set(typo=True)
        with self.assertRaises(ValueError): child.get('typo')
        copy = child.get(); copy['check'] = False
        self.assertTrue(child.check)

    def test_context_defaults_reset_and_script_worker(self):
        old = self.session().get()
        with execution_defaults(check=True, log_level='ERROR'):
            self.assertTrue(self.session().check)
            namespace = sshscript.run_script('from sshscript import Session\ns = Session()\nsettings = s.get()\ns.close()')
            self.assertTrue(namespace['settings']['check'])
        self.assertEqual(self.session().get(), old)

    def test_check_precedence_legacy_managed_and_console(self):
        session = self.session(); session.check = True
        for options in ({}, {'command_timeout': 2}):
            with self.assertRaises(subprocess.CalledProcessError):
                session(['false'], **options)
            self.assertEqual(session(['false'], check=False, **options).exitcode, 1)
        with session.start(['false'], check=False) as job:
            self.assertEqual(job.wait().exitcode, 1)
        with session.shell('bash') as console:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                console('false')
            self.assertEqual(caught.exception.returncode, 1)
            console('false', check=False)
            self.assertEqual(console.exitcode, 1)
            session.check = False
            console('false')

    def test_spy_set_get_and_failure(self):
        with self.assertRaises(subprocess.CalledProcessError):
            sshscript.run_script('with $.shell("bash"):\n    $.set(check=True)\n    $false\n')
        namespace = sshscript.run_script('$.set(check=True)\nvalue = $.get("check")\n$("false", check=False)\n')
        self.assertTrue(namespace['value'])

    def test_spy_thread_inherits_cli_context_defaults(self):
        with execution_defaults(check=True):
            namespace = sshscript.run_script(
                'policy = $.get()\nimport threading\nfrom sshscript import Session\n'
                'values = []\ndef work():\n'
                '    s = Session()\n    values.append(s.get("check"))\n    s.close()\n'
                't = threading.Thread(target=work)\nt.start()\nt.join()\n'
            )
        self.assertEqual(namespace['values'], [True])

    def test_logging_isolation_does_not_mutate_shared_level(self):
        logger = errorutils.get_logger()._logger
        stream = StringIO(); handler = logging.StreamHandler(stream)
        previous = logger.level
        logger.addHandler(handler); logger.setLevel(logging.ERROR)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(logger.setLevel, previous)
        first, second = self.session(), self.session()
        first.log_level = 'DEBUG'; second.log_level = 'ERROR'
        first(['printf', 'first'])
        first.logger.debug('first-marker')
        second.logger.debug('second-marker')
        self.assertIn('Executing subprocess', stream.getvalue())
        self.assertIn('first-marker', stream.getvalue())
        self.assertNotIn('second-marker', stream.getvalue())
        self.assertEqual(logger.level, logging.ERROR)

    def test_managed_verbose_snapshot(self):
        session = self.session(); session.verbose = True
        capture = StringIO()
        with redirect_stdout(capture):
            job = session.start([sys.executable, '-c', 'import time; time.sleep(.1); print("shown")'])
            session.verbose = False
            job.wait()
            session(['printf', 'hidden'], command_timeout=2)
        self.assertEqual(capture.getvalue(), 'shown\n')

    def test_cli_sets_root_and_nested_defaults_without_environment_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'settings.spy'
            path.write_text('from sshscript import Session\nimport os\nprint($.get("verbose"), $.get("log_level"), Session().get("verbose"))\nprint(os.environ.get("VERBOSE"), os.environ.get("DEBUG"))\n$printf visible-output\n$.set(verbose=False)\n$printf hidden-output\n')
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            env.pop('VERBOSE', None); env.pop('DEBUG', None)
            result = subprocess.run([sys.executable, str(Path(sshscript.__file__)), str(path), '-v', '--debug'], env=env, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('True 10 True', result.stdout)
            self.assertIn('None None', result.stdout)
            self.assertIn('visible-output', result.stdout)
            self.assertNotIn('hidden-output', result.stdout)
