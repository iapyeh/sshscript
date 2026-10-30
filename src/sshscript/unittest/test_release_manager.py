"""Offline release orchestration: real disposable Git, fake GitHub/PyPI services."""
import argparse
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'tools/release_manager.py').is_file())
spec = importlib.util.spec_from_file_location('release_manager_under_test', ROOT / 'tools/release_manager.py')
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)

HELPER = '''from pathlib import Path
import shutil
EXTRAS = []
ROOT_FILES = ['README.md', 'CHANGELOG.md', 'tools/prepare_release.py']
def prepare(source, destination):
 source, destination = Path(source), Path(destination)
 package = source / 'src/sshscript' if (source / 'src/sshscript').is_dir() else source
 pairs = [(source / p, p) for p in ['README.md', 'CHANGELOG.md', 'tools/prepare_release.py']]
 pairs += [(package / p, 'src/sshscript/' + p) for p in ['_version.py', 'public.py'] + EXTRAS]
 for original, relative in pairs:
  target = destination / relative
  target.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(original, target)
 return [p for _,p in pairs]
'''


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='sshscript-release-manager-test-')
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name).resolve()
        self.source, self.pub, self.remote = [self.base / p for p in ('main', 'publication', 'remote.git')]
        self.git(self.base, 'init', '--bare', str(self.remote))
        for path, branch in ((self.source, 'main'), (self.pub, 'release')):
            path.mkdir()
            self.git(path, 'init', '-b', branch)
            self.git(path, 'config', 'user.name', 'Public test fixture')
            self.git(path, 'config', 'user.email', 'fixture@example.invalid')
            self.git(path, 'config', 'commit.gpgsign', 'false')
            package = path if branch == 'main' else path / 'src/sshscript'
            package.mkdir(parents=True, exist_ok=True)
            (path / 'tools').mkdir()
            (path / 'tools/prepare_release.py').write_text(HELPER)
            (path / 'README.md').write_text('public instructions\n')
            (path / 'CHANGELOG.md').write_text('# Changes\n## 1.1.0 — test\n\nPublic change\n')
            (package / '_version.py').write_text('__version__ = ' + repr('1.1.0' if branch == 'main' else '1.0.0') + '\n')
            (package / 'public.py').write_text('new public content\n' if branch == 'main' else 'old public content\n')
            self.commit(path, 'Initial public fixture')
        self.git(self.pub, 'remote', 'add', 'origin', str(self.remote))
        self.git(self.pub, 'push', '-u', 'origin', 'release')
        self.state_path = self.base / 'release.json'
        self.operator = manager.Manager(self.state_path, interval=1, timeout=1)
        self.args = argparse.Namespace(version='1.1.0', source=self.source, checkout=self.pub,
                                       repo='example/project', remove_retired=False)
        # Only URL validation is disabled for these local bare Git fixtures.
        real_checkout = manager.checkout
        guard = patch.object(manager, 'checkout', side_effect=lambda path, branch, repo=None: real_checkout(path, branch))
        guard.start()
        self.addCleanup(guard.stop)
        self.base_sha = self.git(self.pub, 'rev-parse', 'HEAD')

    def git(self, root, *args):
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()

    def commit(self, root, message):
        self.git(root, 'add', '--all')
        self.git(root, 'commit', '-m', message)
        return self.git(root, 'rev-parse', 'HEAD')

    def prepare(self):
        with redirect_stdout(io.StringIO()):
            self.operator.prepare(self.args)

    def pr(self, state='OPEN', sha=None):
        return dict(number=5, url='https://example.invalid/pr/5', state=state,
                    headRefOid=sha or self.operator.state['candidate_sha'], baseRefName='release',
                    mergeCommit=None, statusCheckRollup=[])

    def submit(self):
        with patch.object(manager, 'gh', side_effect=lambda *args: [self.pr()]), redirect_stdout(io.StringIO()):
            self.operator.submit()

    def test_prepare_freezes_committed_source_and_preserves_private_files(self):
        (self.source / 'private.spy').write_text('source private fixture')
        (self.pub / 'private.spy').write_text('publication private fixture')
        self.prepare()
        self.assertFalse((self.pub / 'src/sshscript/private.spy').exists())
        self.assertEqual((self.pub / 'private.spy').read_text(), 'publication private fixture')
        (self.source / 'public.py').write_text('later, unselected commit\n')
        self.commit(self.source, 'Later source')
        self.prepare()
        self.assertEqual((self.pub / 'src/sshscript/public.py').read_text(), 'new public content\n')
        self.assertEqual(self.git(self.pub, 'diff', '--cached', '--name-only'), '')

    def test_untracked_collision_stops_before_copying(self):
        (self.source / 'tools/prepare_release.py').write_text(HELPER.replace('EXTRAS = []', "EXTRAS = ['new.py']"))
        (self.source / 'new.py').write_text('public new module')
        self.commit(self.source, 'New public module')
        private = self.pub / 'src/sshscript/new.py'
        private.write_text('pre-existing untracked fixture')
        with self.assertRaisesRegex(manager.ReleaseError, 'Untracked'):
            self.prepare()
        self.assertEqual(private.read_text(), 'pre-existing untracked fixture')
        self.assertFalse(self.state_path.exists())
        self.assertEqual((self.pub / 'src/sshscript/public.py').read_text(), 'old public content\n')

    def test_interrupted_copy_resumes_saved_plan(self):
        original = manager.shutil.copy2
        calls = []
        def interrupted(src, dst, **kw):
            if Path(dst).is_relative_to(self.pub):
                calls.append(dst)
                if len(calls) == 2:
                    raise KeyboardInterrupt()
            return original(src, dst, **kw)
        with patch.object(manager.shutil, 'copy2', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.prepare()
        self.assertTrue(self.state_path.exists())
        self.operator = manager.Manager(self.state_path)
        self.prepare()
        self.operator.validate_plan()

    def test_manual_prepared_change_and_committed_extra_are_rejected(self):
        self.prepare()
        (self.pub / 'src/sshscript/public.py').write_text('manual modification')
        with self.assertRaisesRegex(manager.ReleaseError, 'changed outside'):
            self.operator.submit()
        (self.pub / 'src/sshscript/public.py').write_text('new public content\n')
        extra = self.pub / 'extra.txt'
        extra.write_text('unreviewed committed fixture')
        self.git(self.pub, 'add', 'extra.txt')
        self.git(self.pub, 'commit', '-m', 'Unrelated local commit')
        extra.unlink()  # Net working-tree diff from baseline hides this extra commit.
        with self.assertRaisesRegex(manager.ReleaseError, 'outside the release allowlist'):
            self.operator.submit()

    def test_source_branch_and_version_guards(self):
        self.args.version = '1.2.0'
        with self.assertRaisesRegex(manager.ReleaseError, 'committed main version'):
            self.prepare()
        self.assertFalse(self.state_path.exists())
        self.args.version = '1.1.0.dev1'
        with self.assertRaisesRegex(manager.ReleaseError, 'stable'):
            self.prepare()
        self.args.version = '1.1.0'
        self.git(self.source, 'switch', '-c', 'wrong-branch')
        with self.assertRaisesRegex(manager.ReleaseError, 'main branch'):
            self.prepare()

    def test_submit_does_not_publish_preexisting_local_history(self):
        private = self.pub / 'historical-fixture.txt'
        private.write_text('synthetic private historical content')
        old = self.commit(self.pub, 'Pre-existing local commit')
        private.unlink()
        self.commit(self.pub, 'Remove synthetic historical fixture')
        self.prepare()
        self.submit()
        state = self.operator.state
        candidate = state['candidate_sha']
        self.assertEqual(self.git(self.pub, 'rev-parse', candidate + '^'), self.base_sha)
        ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', old, candidate], cwd=self.pub)
        self.assertEqual(ancestor.returncode, 1)
        self.assertEqual(self.git(self.pub, 'rev-parse', candidate + '^{tree}'), self.git(self.pub, 'rev-parse', 'HEAD^{tree}'))
        before = state['candidate_sha']
        self.submit()
        self.assertEqual(self.operator.state['candidate_sha'], before)
        self.assertEqual(self.git(self.remote, 'rev-parse', 'refs/heads/' + state['branch']), before)

    def test_remote_branch_mismatch_never_force_pushes(self):
        self.prepare()
        branch = self.operator.state['branch']
        self.git(self.pub, 'push', 'origin', f'{self.base_sha}:refs/heads/{branch}')
        with self.assertRaisesRegex(manager.ReleaseError, 'no force push'):
            self.submit()
        self.assertEqual(self.git(self.remote, 'rev-parse', 'refs/heads/' + branch), self.base_sha)

    def test_push_failure_can_resume_without_new_commit(self):
        self.prepare()
        original = manager.git
        def fail_push(root, *args):
            if args[0] == 'push':
                raise manager.ReleaseError('synthetic network failure')
            return original(root, *args)
        with patch.object(manager, 'git', side_effect=fail_push):
            with self.assertRaisesRegex(manager.ReleaseError, 'network'):
                self.submit()
        state = json.loads(self.state_path.read_text())
        self.submit()
        self.assertEqual(self.operator.state['candidate_sha'], state['candidate_sha'])
        self.assertEqual(self.git(self.pub, 'rev-parse', 'HEAD'), state['publication_head'])

    def test_retired_public_input_requires_explicit_flag(self):
        helper = self.pub / 'tools/prepare_release.py'
        helper.write_text(HELPER.replace('EXTRAS = []', "EXTRAS = ['retired.py']"))
        retired = self.pub / 'src/sshscript/retired.py'
        retired.write_text('old public module')
        self.commit(self.pub, 'Previous public layout')
        self.git(self.pub, 'push', 'origin', 'release')
        with self.assertRaisesRegex(manager.ReleaseError, 'Retired public inputs'):
            self.prepare()
        self.assertTrue(retired.exists())
        self.args.remove_retired = True
        self.prepare()
        self.assertFalse(retired.exists())
        self.submit()
        self.assertNotIn('retired.py', self.git(self.pub, 'ls-tree', '-r', '--name-only', self.operator.state['candidate_sha']))

    @contextmanager
    def merged_remote(self, wrong_tree=False):
        self.prepare()
        self.submit()
        tree = self.git(self.pub, 'rev-parse', (self.base_sha if wrong_tree else self.operator.state['candidate_sha']) + '^{tree}')
        merged = self.git(self.pub, 'commit-tree', tree, '-p', self.base_sha, '-m', 'Synthetic protected squash merge')
        self.git(self.pub, 'push', 'origin', merged + ':refs/heads/release')
        pr = self.pr('MERGED')
        pr['mergeCommit'] = dict(oid=merged)
        with patch.object(manager, 'gh', return_value=pr), redirect_stdout(io.StringIO()):
            yield merged

    def test_merged_release_tag_is_annotated_exact_and_resumable(self):
        with self.merged_remote() as merged:
            self.operator.merge_tag()
            self.operator.merge_tag()
        self.assertEqual(self.git(self.remote, 'rev-parse', 'v1.1.0^{}'), merged)
        self.assertEqual(self.git(self.remote, 'cat-file', '-t', 'v1.1.0'), 'tag')

    def test_changed_merge_tree_or_wrong_existing_tag_never_retags(self):
        with self.merged_remote(wrong_tree=True):
            with self.assertRaisesRegex(manager.ReleaseError, 'tree differs'):
                self.operator.merge_tag()
        self.assertEqual(self.git(self.remote, 'tag'), '')

    def test_existing_tag_can_resume_after_release_advances(self):
        with self.merged_remote() as merged:
            self.operator.merge_tag()
            del self.operator.state['tag']  # Simulate losing the tag-push response before state save.
            tree=self.git(self.pub,'rev-parse',merged+'^{tree}')
            advanced=self.git(self.pub,'commit-tree',tree,'-p',merged,'-m','Later release metadata')
            self.git(self.pub,'push','origin',advanced+':refs/heads/release')
            self.operator.merge_tag()
        self.assertEqual(self.git(self.remote,'rev-parse','v1.1.0^{}'),merged)

    def test_new_tag_is_not_created_when_release_advanced(self):
        with self.merged_remote() as merged:
            tree=self.git(self.pub,'rev-parse',merged+'^{tree}')
            advanced=self.git(self.pub,'commit-tree',tree,'-p',merged,'-m','Later release metadata')
            self.git(self.pub,'push','origin',advanced+':refs/heads/release')
            with self.assertRaisesRegex(manager.ReleaseError,'release advanced'):
                self.operator.merge_tag()
        self.assertEqual(self.git(self.remote,'tag'),'')

    def test_recover_merged_pr_and_existing_tag_without_new_publication(self):
        with self.merged_remote() as merged:
            self.operator.merge_tag()
            self.git(self.pub,'push','origin',self.operator.state['candidate_sha']+':refs/pull/5/head')
            pr=self.pr('MERGED');pr['mergeCommit']=dict(oid=merged);pr['headRefName']=self.operator.state['branch']
            restored=manager.Manager(self.base/'recovered.json')
            args=argparse.Namespace(version='1.1.0',repo='example/project',checkout=self.pub,pr=5)
            with patch.object(manager,'gh',return_value=pr):
                restored.recover(args)
        self.assertEqual(restored.state['merge_sha'],merged)
        self.assertEqual(restored.state['tag'],'v1.1.0')
        with self.assertRaisesRegex(manager.ReleaseError,'new state path'):
            restored.recover(args)

    def test_wrong_existing_remote_tag_is_preserved(self):
        with self.merged_remote():
            self.git(self.pub, 'tag', '-a', 'v1.1.0', self.base_sha, '-m', 'Wrong fixture tag')
            self.git(self.pub, 'push', 'origin', 'refs/tags/v1.1.0')
            with self.assertRaisesRegex(manager.ReleaseError, 'never replaced'):
                self.operator.merge_tag()
        self.assertEqual(self.git(self.remote, 'rev-parse', 'v1.1.0^{}'), self.base_sha)

    def docs_prepare(self, paths=None):
        self.git(self.source, 'branch', '-m', 'working_branch')
        self.docs = manager.DocsManager(self.base / 'docs.json', interval=1, timeout=1)
        self.docs_args = argparse.Namespace(source=self.source, checkout=self.pub,
                                           repo='example/project', message='Clarify status spelling',
                                           files=paths or ['README.md'])
        with redirect_stdout(io.StringIO()):
            self.docs.prepare_docs(self.docs_args)

    def test_docs_plan_preserves_unrelated_changes_and_publication_index(self):
        (self.source / 'README.md').write_text('Use exitcode.\n')
        (self.source / 'public.py').write_text('unrelated source change\n')
        (self.pub / 'README.md').write_text('unrelated publication change\n')
        self.git(self.pub, 'add', 'README.md')
        index = self.git(self.pub, 'write-tree')
        self.docs_prepare()
        self.assertEqual(self.git(self.pub, 'write-tree'), index)
        self.assertEqual(self.git(self.pub, 'rev-parse', 'HEAD'), self.base_sha)
        self.assertEqual(self.git(self.source, 'log', '-1', '--format=%s'), 'Initial public fixture')
        self.assertEqual(self.git(self.pub, 'show', self.docs.state['docs_tree'] + ':README.md'), 'Use exitcode.')
        self.assertEqual(self.git(self.pub, 'diff-tree', '--no-commit-id', '--name-only', '-r',
                                  self.base_sha + '^{tree}', self.docs.state['docs_tree']), 'README.md')

    def test_docs_rejects_code_unlisted_markdown_and_source_staging(self):
        for paths in (['public.py'], ['private.md']):
            with self.subTest(paths=paths):
                self.git(self.source, 'branch', '-m', 'main')
                with self.assertRaisesRegex(manager.ReleaseError, 'allowlisted Markdown'):
                    self.docs_prepare(paths)
        self.git(self.source, 'branch', '-m', 'main')
        (self.source / 'README.md').write_text('staged\n')
        self.git(self.source, 'add', 'README.md')
        with self.assertRaisesRegex(manager.ReleaseError, 'staged'):
            self.docs_prepare()
        self.assertFalse((self.base / 'docs.json').exists())

    def test_docs_rejects_remote_drift_and_symlinks(self):
        (self.pub / 'README.md').write_text('new upstream prose\n')
        self.commit(self.pub, 'Upstream docs')
        self.git(self.pub, 'push', 'origin', 'release')
        (self.source / 'README.md').write_text('local edit\n')
        with self.assertRaisesRegex(manager.ReleaseError, 'reconcile'):
            self.docs_prepare()
        self.assertFalse(self.docs.path.exists())
        self.git(self.source, 'branch', '-m', 'main')
        (self.source / 'README.md').unlink()
        (self.source / 'README.md').symlink_to(self.source / 'public.py')
        with self.assertRaisesRegex(manager.ReleaseError, 'escapes'):
            self.docs_prepare()

    def test_docs_changed_plan_stops_before_local_commit_or_push(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        (self.source / 'README.md').write_text('unreviewed prose\n')
        with self.assertRaisesRegex(manager.ReleaseError, 'changed after planning'):
            self.docs.finish_docs()
        self.assertEqual(self.git(self.source, 'log', '-1', '--format=%s'), 'Initial public fixture')
        self.assertEqual(self.git(self.remote, 'for-each-ref', '--format=%(refname)', 'refs/heads'), 'refs/heads/release')

    @contextmanager
    def docs_services(self, fail_merge=False):
        merged = [False]
        original_run = manager.run
        def pr():
            state = self.docs.state
            return dict(number=9, url='https://example.invalid/pr/9',
                        headRefOid=state['candidate_sha'], baseRefName='release',
                        state='MERGED' if merged[0] else 'OPEN',
                        mergeCommit=dict(oid=merged[0]) if merged[0] else None,
                        statusCheckRollup=[])
        def github(*args):
            if args[:2] == ('pr', 'list'):
                return [pr()]
            if args[:2] == ('pr', 'view'):
                return pr()
            raise AssertionError(args)
        def commands(*args, **kwargs):
            if args[:3] == ('gh', 'pr', 'merge'):
                if fail_merge:
                    raise manager.ReleaseError('synthetic merge failure')
                state = self.docs.state
                parent = self.git(self.remote, 'rev-parse', 'refs/heads/release')
                merged[0] = self.git(self.pub, 'commit-tree', state['docs_tree'], '-p', parent, '-m', 'Merge docs')
                self.git(self.pub, 'push', 'origin', merged[0] + ':refs/heads/release')
                return ''
            if args[0] == 'gh':
                raise AssertionError('Unexpected remote operation: ' + repr(args))
            return original_run(*args, **kwargs)
        with patch.object(manager, 'gh', side_effect=github), patch.object(manager, 'run', side_effect=commands), \
                patch.object(self.docs, 'ci_once', return_value=(True, 'CI passed')), redirect_stdout(io.StringIO()):
            yield

    def test_docs_finish_commits_only_selected_docs_without_version_or_tags(self):
        (self.source / 'README.md').write_text('Use exitcode.\n')
        (self.source / 'public.py').write_text('private uncommitted change\n')
        (self.source / 'private.spy').write_text('private untracked input\n')
        self.docs_prepare()
        with self.docs_services():
            self.docs.finish_docs()
        state = self.docs.state
        self.assertEqual(self.git(self.source, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'), 'README.md')
        self.assertIn('public.py', self.git(self.source, 'diff', '--name-only'))
        self.assertTrue((self.source / 'private.spy').exists())
        self.assertEqual(self.git(self.pub, 'rev-parse', 'HEAD'), self.base_sha)
        self.assertEqual(self.git(self.remote, 'show', 'release:src/sshscript/_version.py'), "__version__ = '1.0.0'")
        self.assertEqual(self.git(self.remote, 'show', 'release:src/sshscript/public.py'), 'old public content')
        self.assertEqual(self.git(self.remote, 'tag'), '')
        self.assertEqual(self.git(self.remote, 'rev-parse', 'release'), state['merge_sha'])

    def test_docs_push_failure_resumes_same_source_and_candidate_commits(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        original_git = manager.git
        def fail_push(root, *args):
            if args[0] == 'push':
                raise manager.ReleaseError('synthetic network failure')
            return original_git(root, *args)
        with patch.object(manager, 'git', side_effect=fail_push):
            with self.assertRaisesRegex(manager.ReleaseError, 'network failure'):
                self.docs.finish_docs()
        source_sha = self.docs.state['source_commit']
        candidate = self.docs.state['candidate_sha']
        with self.docs_services():
            self.docs.finish_docs()
        self.assertEqual(self.docs.state['candidate_sha'], candidate)
        self.assertEqual(self.git(self.source, 'rev-parse', 'HEAD'), source_sha)

    def test_docs_noop_and_executable_documents_are_rejected(self):
        with self.assertRaisesRegex(manager.ReleaseError, 'already match'):
            self.docs_prepare()
        self.git(self.source, 'branch', '-m', 'main')
        (self.source / 'README.md').chmod(0o755)
        self.commit(self.source, 'Executable document')
        with self.assertRaisesRegex(manager.ReleaseError, 'non-executable'):
            self.docs_prepare()

    def test_docs_permission_change_after_plan_stops_before_commit(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        (self.source / 'README.md').chmod(0o755)
        with self.assertRaisesRegex(manager.ReleaseError, 'non-executable'):
            self.docs.finish_docs()
        self.assertEqual(self.git(self.source, 'log', '-1', '--format=%s'), 'Initial public fixture')
        self.assertEqual(self.git(self.remote, 'rev-parse', 'release'), self.base_sha)

    def test_docs_new_allowlisted_document_is_committed_and_published(self):
        # Both fixture preparation manifests already allow CHANGELOG.md.
        self.git(self.source, 'rm', 'CHANGELOG.md')
        self.commit(self.source, 'Remove fixture changelog')
        self.git(self.pub, 'rm', 'CHANGELOG.md')
        self.commit(self.pub, 'Remove remote fixture changelog')
        self.git(self.pub, 'push', 'origin', 'release')
        (self.source / 'CHANGELOG.md').write_text('New public document\n')
        self.docs_prepare(['CHANGELOG.md'])
        with self.docs_services():
            self.docs.finish_docs()
        self.assertEqual(self.git(self.remote, 'show', 'release:CHANGELOG.md'), 'New public document')
        self.assertEqual(self.git(self.source, 'status', '--porcelain'), '')

    def test_docs_ci_failure_keeps_release_and_tags_unchanged(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        with self.docs_services(), patch.object(self.docs, 'ci_once', side_effect=manager.ReleaseError('CI failed')):
            with self.assertRaisesRegex(manager.ReleaseError, 'CI failed'):
                self.docs.finish_docs()
        self.assertEqual(self.git(self.remote, 'rev-parse', 'release'), self.base_sha)
        self.assertEqual(self.git(self.remote, 'tag'), '')

    def test_docs_remote_branch_collision_never_force_pushes(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        branch = self.docs.state['branch']
        self.git(self.pub, 'push', 'origin', self.base_sha + ':refs/heads/' + branch)
        with self.assertRaisesRegex(manager.ReleaseError, 'no force push'):
            self.docs.finish_docs()
        self.assertEqual(self.git(self.remote, 'rev-parse', branch), self.base_sha)

    def test_docs_interruption_after_staging_resumes_selected_files(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        self.git(self.source, 'add', 'README.md')
        with self.docs_services():
            self.docs.finish_docs()
        self.assertEqual(self.git(self.source, 'status', '--porcelain'), '')

    def test_docs_source_move_and_unrelated_staging_block_publication(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        (self.source / 'public.py').write_text('unrelated fixture\n')
        self.git(self.source, 'add', 'public.py')
        with self.assertRaisesRegex(manager.ReleaseError, 'unrelated staged'):
            self.docs.finish_docs()
        self.git(self.source, 'commit', '-m', 'Unrelated change after plan')
        with self.assertRaisesRegex(manager.ReleaseError, 'HEAD moved'):
            self.docs.finish_docs()
        self.assertEqual(self.git(self.remote, 'rev-parse', 'release'), self.base_sha)

    def test_docs_saved_plan_reloads_and_finishes_in_a_new_instance(self):
        (self.source / 'README.md').write_text('Use exitcode.\n')
        self.docs_prepare()
        state_path = self.docs.path
        self.assertNotIn('version', json.loads(state_path.read_text()))
        self.docs = manager.DocsManager(state_path, interval=1, timeout=1)
        with self.docs.lock(), self.docs_services():
            self.docs.finish_docs()
        restored = manager.DocsManager(state_path)
        self.assertEqual(self.git(self.remote, 'rev-parse', 'release'), restored.state['merge_sha'])
        self.assertEqual(self.git(self.remote, 'tag'), '')

    def test_docs_finish_cli_reads_saved_plan_and_reloads_under_lock(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        with patch.object(manager.DocsManager, 'finish_docs', autospec=True) as finish:
            self.assertEqual(manager.main(['--state', str(self.docs.path), 'docs-finish', '--push']), 0)
        finish.assert_called_once()
        self.assertEqual(finish.call_args.args[0].state['docs_tree'], self.docs.state['docs_tree'])
        self.assertEqual(self.git(self.source, 'log', '-1', '--format=%s'), 'Initial public fixture')

    def test_release_state_still_requires_a_valid_version(self):
        state = self.base / 'invalid-release.json'
        for version in (None, '', '1.0', '1.0.0.dev1'):
            value = dict(schema_version=1, repo='example/project')
            if version is not None:
                value['version'] = version
            state.write_text(json.dumps(value))
            with self.subTest(version=version), self.assertRaisesRegex(manager.ReleaseError, 'Invalid version'):
                manager.Manager(state)

    def test_docs_workflow_state_cannot_enter_version_release(self):
        (self.source / 'README.md').write_text('selected prose\n')
        self.docs_prepare()
        with patch.object(manager.Manager, 'merge_tag') as release, redirect_stderr(io.StringIO()):
            self.assertEqual(manager.main(['--state', str(self.docs.path), 'merge-tag']), 1)
        release.assert_not_called()



class OfflinePolicyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.operator = manager.Manager(self.root / 'release.json', interval=1, timeout=1)
        self.operator.state = dict(schema_version=1, version='1.1.0', repo='example/project',
                                   candidate_sha='a'*40, merge_sha='b'*40, tag='v1.1.0', branch='candidate', pr=5, notes='Public test release notes')

    def test_checks_fail_closed_for_skips_cancellation_and_empty_lists(self):
        self.assertTrue(manager.classify_checks([])[0])
        for conclusion in ('FAILURE','CANCELLED','SKIPPED','NEUTRAL','TIMED_OUT',None):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(manager.classify_checks([dict(name='check',status='COMPLETED',conclusion=conclusion)])[1], ['check'])
        self.assertEqual(manager.classify_checks([dict(context='legacy',state='ERROR')])[1], ['legacy'])

    def test_all_current_checks_green_is_not_enough_until_ci_workflow_finishes(self):
        pr = dict(url='fixture', statusCheckRollup=[dict(name='check',status='COMPLETED',conclusion='SUCCESS')])
        with patch.object(self.operator, 'pr', return_value=pr), patch.object(self.operator, 'workflow_run', return_value=dict(id=1,status='in_progress')):
            self.assertFalse(self.operator.ci_once()[0])
        with patch.object(self.operator, 'pr', return_value=pr), patch.object(self.operator, 'workflow_run', return_value=dict(id=1,status='completed',conclusion='success')):
            self.assertTrue(self.operator.ci_once()[0])

    def test_workflow_selection_is_pinned_to_commit_branch_and_event(self):
        runs = [dict(id=i,head_sha=sha,head_branch=branch,event=event) for i,sha,branch,event in
                [(1,'b'*40,'v1.1.0','push'),(2,'c'*40,'v1.1.0','push'),(3,'b'*40,'other','push'),(4,'b'*40,'v1.1.0','workflow_dispatch')]]
        with patch.object(manager, 'api', return_value=dict(workflow_runs=runs)):
            self.assertEqual(self.operator.workflow_run('release.yml','b'*40,'v1.1.0','push')['id'],1)

    def test_changed_pr_head_is_rejected(self):
        with patch.object(manager, 'gh', return_value=dict(headRefOid='c'*40,baseRefName='release',state='OPEN')):
            with self.assertRaisesRegex(manager.ReleaseError, 'head/base changed'):
                self.operator.pr()

    def test_approval_stop_has_dedicated_exit_code_without_remote_action(self):
        self.operator.save()
        with patch.object(manager.Manager, 'release_once', side_effect=manager.ApprovalNeeded('waiting for approval')), redirect_stderr(io.StringIO()):
            self.assertEqual(manager.main(['--state',str(self.operator.path),'wait-release']),3)

    def test_wait_timeout_retains_state(self):
        self.operator.save()
        with patch.object(manager.time, 'monotonic', side_effect=[0,2]), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(manager.ReleaseError, 'timed out'):
                self.operator.poll(lambda: (False,'pending'))
        self.assertTrue(self.operator.path.exists())

    def test_state_is_private_atomic_and_reloaded_under_lock(self):
        self.operator.save()
        self.assertEqual(self.operator.path.stat().st_mode & 0o777, 0o600)
        other = manager.Manager(self.operator.path)
        self.operator.state['verified'] = True
        self.operator.save()
        with other.lock():
            self.assertTrue(other.state['verified'])
        with self.operator.lock():
            with self.assertRaisesRegex(manager.ReleaseError, 'Another command'):
                with other.lock():
                    pass

    def test_unsupported_state_and_invalid_commit_are_rejected(self):
        self.operator.save()
        value = json.loads(self.operator.path.read_text())
        value['candidate_sha'] = '--not-a-commit'
        self.operator.path.write_text(json.dumps(value))
        with self.assertRaisesRegex(manager.ReleaseError, 'commit identity'):
            manager.Manager(self.operator.path)

    def test_approval_requires_right_environment_permission_and_successful_gates(self):
        pending = [dict(environment=dict(id=10,name='production'),current_user_can_approve=True)]
        with patch.object(self.operator, 'release_run', return_value=dict(id=1)), patch.object(manager, 'api', return_value=pending):
            with self.assertRaisesRegex(manager.ReleaseError, 'one pypi'):
                self.operator.approve()
        pending[0]['environment']['name']='pypi'
        jobs=dict(jobs=[dict(name='Verify and attest release artifacts',status='completed',conclusion='failure')])
        with patch.object(self.operator, 'release_run', return_value=dict(id=1)), patch.object(manager, 'api', side_effect=[pending,jobs]), patch.object(self.operator,'assets') as assets:
            with self.assertRaisesRegex(manager.ReleaseError, 'gates'):
                self.operator.approve()
            assets.assert_not_called()

    def test_asset_tampering_and_mismatched_wheel_metadata_block_approval(self):
        self.operator.save()
        folder=self.operator.path.parent/(self.operator.path.stem+'-artifacts')
        folder.mkdir()
        wheel='sshscript-1.1.0-py3-none-any.whl'; sdist='sshscript-1.1.0.tar.gz'
        with zipfile.ZipFile(folder/wheel,'w') as z:
            z.writestr('sshscript-1.1.0.dist-info/METADATA','Name: sshscript\nVersion: 9.9.9\n')
        (folder/sdist).write_bytes(b'public fixture sdist')
        manifest={name:manager.digest(folder/name) for name in (wheel,sdist)}
        (folder/'verified.json').write_text(json.dumps(manifest))
        with patch.object(manager,'gh',return_value=dict(tagName='v1.1.0',isDraft=True)),patch.object(manager,'run'):
            with self.assertRaisesRegex(manager.ReleaseError,'metadata'):
                self.operator.assets()
            (folder/sdist).write_bytes(b'changed after verification')
            with self.assertRaisesRegex(manager.ReleaseError,'hash mismatch'):
                self.operator.assets()

    def test_verify_rejects_yanked_or_mismatched_public_artifacts(self):
        filename='sshscript-1.1.0-py3-none-any.whl'; manifest={filename:'a'*64}
        item=dict(filename=filename,digests=dict(sha256='b'*64),yanked=False,url='https://files.pythonhosted.org/fixture')
        metadata=dict(info=dict(version='1.1.0'),urls=[item])
        with patch.object(self.operator,'release_once',return_value=(True,'done')),patch.object(self.operator,'assets',return_value=(dict(isDraft=False),self.root,manifest)),patch.object(manager.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(metadata).encode())):
            with self.assertRaisesRegex(manager.ReleaseError,'hash mismatch'):
                self.operator.verify()
        self.assertNotIn('verified',self.operator.state)

    def test_retagged_release_is_rejected(self):
        ref = dict(object=dict(type='tag',sha='d'*40))
        tag = dict(object=dict(type='commit',sha='c'*40))
        with patch.object(manager,'api',side_effect=[ref,tag]):
            with self.assertRaisesRegex(manager.ReleaseError,'tag moved'):
                self.operator.tag_guard()

    def test_approval_reuses_prior_successful_gates_after_failed_job_retry(self):
        pending=[dict(environment=dict(id=42,name='pypi'),current_user_can_approve=True)]
        jobs=dict(jobs=[dict(id=1,name='Verify and attest release artifacts',status='completed',conclusion='success'),
                        dict(id=2,name='Create draft GitHub Release',status='completed',conclusion='success'),
                        dict(id=3,name='Publish distributions to PyPI',status='completed',conclusion='failure'),
                        dict(id=4,name='Publish distributions to PyPI',status='waiting',conclusion=None)])
        actions=[]
        def action(*args,**kwargs):
            if args[:3]==('gh','release','edit'):
                text=Path(args[-1]).read_text()
                self.assertIn('Public test release notes',text)
                self.assertIn('*Last modified:',text)
                actions.append('notes')
            elif args[:2]==('gh','api'):
                body=json.loads(Path(args[-1]).read_text())
                self.assertEqual(body['environment_ids'],[42])
                self.assertEqual(body['state'],'approved')
                actions.append('approve')
            return ''
        with patch.object(self.operator,'release_run',return_value=dict(id=1)),patch.object(manager,'api',side_effect=[pending,jobs]),patch.object(self.operator,'assets',side_effect=lambda:(actions.append('hashes') or (dict(isDraft=True),None,None))),patch.object(manager,'run',side_effect=action),redirect_stdout(io.StringIO()):
            self.operator.approve()
        self.assertEqual(actions,['hashes','notes','approve'])

    def test_no_pending_deployment_is_idempotent(self):
        with patch.object(self.operator,'release_run',return_value=dict(id=1)),patch.object(manager,'api',return_value=[]),redirect_stdout(io.StringIO()):
            self.operator.approve()


if __name__ == '__main__':
    unittest.main()
