"""Offline regressions for CLI update checks and Python compatibility filtering."""
import contextlib
import io
import json
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError

import sshscript


def release(version, requires='>=3.9', yanked=False):
    return {'filename': f'sshscript-{version}-py3-none-any.whl',
            'requires-python': requires, 'yanked': yanked}


class UpdateCheckTests(unittest.TestCase):
    def run_check(self, current, files, option='--check-updates', error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        response = io.StringIO(json.dumps({'files': files}))
        with patch.object(sshscript, '__version__', current), \
             patch.object(sys, 'version_info', (3, 9, 6)), \
             patch.object(sys, 'argv', ['sshscript', option]), \
             patch('urllib.request.urlopen', return_value=response,
                   side_effect=error) as request, \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as result:
                sshscript.main()
        self.assertEqual(request.call_args.kwargs['timeout'], 3)
        return result.exception.code, stdout.getvalue(), stderr.getvalue()

    def test_numeric_and_major_version_ordering(self):
        for current, latest in [('3.9.0', '3.10.0'), ('3.9.0', '4.0.0')]:
            with self.subTest(current=current, latest=latest):
                code, output, error = self.run_check(current, [release(latest)])
                self.assertEqual(code, 0)
                self.assertIn('Upgrade:', output)
                self.assertEqual(output.count('-m pip install --upgrade sshscript'), 1)
                self.assertEqual(error, '')

    def test_filters_python_prerelease_and_yanked(self):
        files = [release('3.2'), release('4.0', '>=3.10'),
                 release('5.0rc1'), release('6.0.dev1'), release('7.0', yanked=True)]
        code, output, _ = self.run_check('3.1', files)
        self.assertEqual(code, 0)
        self.assertIn('Python 3.9.6: 3.2', output)

    def test_equal_or_newer_checkout_does_not_suggest_downgrade(self):
        for current in ['3.2.0', '4.0.dev1']:
            with self.subTest(current=current):
                code, output, _ = self.run_check(current, [release('3.2')])
                self.assertEqual(code, 0)
                self.assertNotIn('Upgrade:', output)

    def test_legacy_alias(self):
        code, output, _ = self.run_check('3.1', [release('3.2')], '--check')
        self.assertEqual(code, 0)
        self.assertIn('Upgrade:', output)

    def test_network_failure_is_concise(self):
        code, output, error = self.run_check('3.1', [], error=URLError('offline'))
        self.assertEqual(code, 1)
        self.assertEqual(output, '')
        self.assertIn('Unable to check for updates: offline', error)
        self.assertNotIn('Traceback', error)

    def test_no_compatible_release(self):
        code, output, _ = self.run_check('3.1', [release('4.0', '>=3.10')])
        self.assertEqual(code, 0)
        self.assertIn('No stable release supports Python 3.9.6', output)

    def test_invalid_response(self):
        code, _, error = self.run_check('3.1', [None])
        self.assertEqual(code, 1)
        self.assertNotIn('Traceback', error)
