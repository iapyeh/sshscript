"""Publication must preserve the regressions and instructions used as evidence."""
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'tools/prepare_release.py').is_file())
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_release import TESTS, prepare, validate_release_inputs, verify_sdist_tests


class ReleaseInputTests(unittest.TestCase):
    def fixture(self, release=False):
        folder = tempfile.TemporaryDirectory(prefix='sshscript-release-inputs-')
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        package = root / 'src/sshscript' if release else root
        tests = package / 'unittest'
        tests.mkdir(parents=True)
        for name in TESTS:
            (tests / name).write_text('public fixture: ' + name)
        (root / 'MANIFEST.in').write_text(''.join(
            'include src/sshscript/unittest/' + name + '\n' for name in TESTS))
        return root, tests

    def test_current_inputs_are_complete(self):
        validate_release_inputs(ROOT)

    def test_both_layouts_accept_explicit_public_inputs(self):
        for release in (False, True):
            root, _ = self.fixture(release)
            validate_release_inputs(root)

    def test_new_discovered_regression_cannot_silently_disappear(self):
        root, tests = self.fixture()
        (tests / 'test_new_contract.py').write_text('')
        with self.assertRaisesRegex(ValueError, 'test_new_contract.py'):
            validate_release_inputs(root)

    def test_missing_instructions_are_rejected(self):
        root, tests = self.fixture()
        (tests / 'README.console-authentication.md').unlink()
        with self.assertRaisesRegex(FileNotFoundError, 'README.console-authentication.md'):
            validate_release_inputs(root)

    def test_manifest_omission_and_broad_inclusion_are_rejected(self):
        for replacement in ('', 'recursive-include src/sshscript/unittest *\n'):
            root, _ = self.fixture()
            (root / 'MANIFEST.in').write_text(replacement)
            with self.assertRaisesRegex(ValueError, 'MANIFEST.in'):
                validate_release_inputs(root)

    def test_preparation_preserves_public_tests_and_excludes_private_files(self):
        with tempfile.TemporaryDirectory(prefix='sshscript-release-stage-') as tmp:
            stage = Path(tmp) / 'stage'
            prepare(ROOT, stage)
            actual = {p.name for p in (stage / 'src/sshscript/unittest').iterdir()}
            self.assertEqual(actual, set(TESTS))
            validate_release_inputs(stage)
            for name in TESTS:
                self.assertEqual((stage / 'src/sshscript/unittest' / name).read_bytes(),
                                 (ROOT / ('src/sshscript' if (ROOT / 'src/sshscript').is_dir() else '') / 'unittest' / name).read_bytes())

    def archive(self, tests, omitted=None, altered=None, extra=False):
        archive = tests.parent.parent / 'candidate.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for name in TESTS:
                if name != omitted:
                    tar.add(tests / name, arcname='candidate/src/sshscript/unittest/' + name)
            if extra:
                private = tests / 'private-hosts.py'
                private.write_text('private sentinel')
                tar.add(private, arcname='candidate/src/sshscript/unittest/private-hosts.py')
        if altered:
            (tests / altered).write_text('changed after build')
        return archive

    def test_sdist_preserves_exact_inputs(self):
        root, tests = self.fixture(True)
        verify_sdist_tests(root, self.archive(tests))

    def test_sdist_rejects_missing_changed_or_unapproved_inputs(self):
        for options in ({'omitted': 'test_console_results.py'},
                        {'altered': 'test_console_authentication.py'}, {'extra': True}):
            root, tests = self.fixture(True)
            with self.assertRaisesRegex(ValueError, 'sdist'):
                verify_sdist_tests(root, self.archive(tests, **options))


if __name__ == '__main__':
    unittest.main()
