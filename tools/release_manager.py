"""Resumable maintainer CLI for documentation PRs and version publication."""
import argparse
import ast
from contextlib import contextmanager
from datetime import datetime
import fcntl
import email
import hashlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import venv
import zipfile
from zoneinfo import ZoneInfo

VERSION = re.compile(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z')
REPO = re.compile(r'[\w.-]+/[\w.-]+\Z')


class ReleaseError(RuntimeError):
    pass


def run(*args, cwd=None, capture=True):
    environment = os.environ.copy()
    environment['GIT_OPTIONAL_LOCKS'] = '0'
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=environment, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if result.returncode:
        raise ReleaseError(f'Command failed ({result.returncode}): {args[0]} {args[1] if len(args)>1 else ""}\n'
                           + (result.stderr or 'See command output above.'))
    return (result.stdout or '').strip()


def git(root, *args):
    return run('git', *args, cwd=root)


def gh(*args):
    return json.loads(run('gh', *args))


def api(repo, suffix):
    return gh('api', f'repos/{repo}/{suffix}')


def digest(path):
    if path.is_symlink() or not path.is_file():
        if path.exists() or path.is_symlink():
            raise ReleaseError(f'Expected a regular file: {path}')
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version_at(root):
    path = root / 'src/sshscript/_version.py'
    if not path.exists():
        path = root / '_version.py'
    return version_text(path.read_text())


def version_text(text):
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ReleaseError('Cannot read the package version')


def checkout(path, branch, repo=None):
    path = Path(path).expanduser().resolve()
    if git(path, 'rev-parse', '--show-toplevel') != str(path) or git(path, 'branch', '--show-current') != branch:
        raise ReleaseError(f'Requires the {branch} branch at repository root: {path}')
    if repo:
        remote = git(path, 'remote', 'get-url', 'origin')
        if remote not in (f'https://github.com/{repo}.git', f'https://github.com/{repo}', f'git@github.com:{repo}.git'):
            raise ReleaseError('origin does not match the configured GitHub repository')
    return path


def clean(root):
    if git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ReleaseError('Tracked/index changes need review before this operation')


def destination(root, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0] == '.git':
        raise ReleaseError('Invalid release input path')
    path = root / relative
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ReleaseError(f'Release input escapes the checkout: {name}')
    return path


@contextmanager
def snapshot(root, sha):
    with tempfile.TemporaryDirectory(prefix='sshscript-committed-source-') as folder:
        archive = subprocess.check_output(['git', 'archive', sha], cwd=root)
        target = Path(folder)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            options = {'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}
            stream.extractall(target, **options)
        yield target


def layout(source, output):
    helper = runpy.run_path(str(source / 'tools/prepare_release.py'))
    return helper['prepare'](source, output)


def classify_checks(checks):
    pending, failed = [], []
    for check in checks:
        name = check.get('name', check.get('context', 'unknown check'))
        if 'status' in check:
            if check['status'] != 'COMPLETED':
                pending.append(name)
            elif check.get('conclusion') != 'SUCCESS':
                failed.append(name)
        elif check.get('state') == 'PENDING':
            pending.append(name)
        elif check.get('state') != 'SUCCESS':
            failed.append(name)
    if not checks:
        pending.append('checks have not appeared yet')
    return pending, failed


class Manager:
    def __init__(self, path, interval=60, timeout=0):
        self.path = Path(path).expanduser().resolve()
        self.interval, self.timeout = interval, timeout
        self.load()

    def load(self):
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        if self.state and self.state.get('schema_version') != 1:
            raise ReleaseError('Unsupported state schema; use its matching tool')
        if self.state:
            mode = self.state.get('mode')
            if mode not in (None, 'docs'):
                raise ReleaseError('Unsupported workflow mode in state')
            repo = self.state.get('repo')
            if not isinstance(repo, str) or not REPO.fullmatch(repo):
                raise ReleaseError('Invalid repository in state')
            if mode != 'docs':
                version = self.state.get('version')
                if not isinstance(version, str) or not VERSION.fullmatch(version):
                    raise ReleaseError('Invalid version in release state')
            for key in ('source_sha', 'baseline_sha', 'remote_base_sha', 'candidate_sha', 'publication_head', 'merge_sha', 'source_commit', 'docs_tree'):
                if key in self.state and not re.fullmatch('[0-9a-f]{40}', self.state[key]):
                    raise ReleaseError('Invalid commit identity in state: ' + key)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state['updated_at'] = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
        with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump(self.state, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    @contextmanager
    def lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.path) + '.lock', 'a') as stream:
            os.chmod(stream.name, 0o600)
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ReleaseError('Another command is using this state file') from None
            self.load()  # Another process may have saved a newer state before this lock.
            yield

    def require(self, *keys):
        if any(key not in self.state for key in keys):
            raise ReleaseError('Missing release state; run the preceding step first')

    @property
    def repo(self):
        self.require('repo')
        return self.state['repo']

    @property
    def root(self):
        self.require('checkout')
        return checkout(self.state['checkout'], 'release', self.repo)

    def poll(self, operation):
        start, previous = time.monotonic(), None
        while True:
            done, message = operation()
            if message != previous:
                print(message, flush=True)
                previous = message
            if done:
                return
            if self.timeout and time.monotonic() - start >= self.timeout:
                raise ReleaseError('Wait timed out; rerun the same command to resume')
            time.sleep(self.interval)

    def prepare(self, args):
        if not VERSION.fullmatch(args.version) or not REPO.fullmatch(args.repo):
            raise ReleaseError('Use a stable X.Y.Z version and owner/repository')
        source = checkout(args.source, 'main')
        root = checkout(args.checkout, 'release', args.repo)
        if source == root:
            raise ReleaseError('Source and publication checkouts must differ')
        if self.state:
            expected = (args.version, str(source), str(root), args.repo)
            actual = tuple(self.state.get(k) for k in ('version', 'source', 'checkout', 'repo'))
            if expected != actual or self.state.get('candidate_sha'):
                raise ReleaseError('State belongs to an existing release; resume it or choose a new --state path')
        else:
            clean(source)
            clean(root)
            git(root, 'fetch', 'origin', 'release')
            # Integrate prior squash history only when it changes no files, or is a fast-forward.
            if git(root, 'rev-parse', 'HEAD^{tree}') == git(root, 'rev-parse', 'origin/release^{tree}'):
                git(root, 'merge', '--no-edit', 'origin/release')
            else:
                git(root, 'merge', '--ff-only', 'origin/release')
            clean(root)
            if git(root, 'rev-parse', 'HEAD^{tree}') != git(root, 'rev-parse', 'origin/release^{tree}'):
                raise ReleaseError('Publication tree contains unpublished commits; finish its existing state or use a clean release checkout')
            if git(root, 'ls-remote', 'origin', f'refs/tags/v{args.version}'):
                raise ReleaseError('This version already has a remote tag; use its existing state/status')
            source_sha = git(source, 'rev-parse', 'HEAD')
            with snapshot(source, source_sha) as frozen, tempfile.TemporaryDirectory() as tmp:
                if version_at(frozen) != args.version:
                    raise ReleaseError('The committed main version must equal --version; this tool never bumps it')
                stage = Path(tmp) / 'new'
                paths = layout(frozen, stage)
                baseline = git(root, 'rev-parse', 'HEAD')
                with snapshot(root, baseline) as old:
                    old_paths = layout(old, Path(tmp) / 'old')
                retired = sorted(set(old_paths) - set(paths))
                if retired and not args.remove_retired:
                    raise ReleaseError('Retired public inputs need review; rerun with --remove-retired: ' + ', '.join(retired))
                tracked = set(git(root, 'ls-files').splitlines())
                before, after = {}, {}
                for name in sorted(set(paths) | set(retired)):
                    target = destination(root, name)
                    before[name] = digest(target)
                    if before[name] is not None and name not in tracked:
                        raise ReleaseError(f'Untracked file would be overwritten: {name}')
                    after[name] = digest(stage / name) if name in paths else None
                self.state = dict(schema_version=1, version=args.version, repo=args.repo,
                                  source=str(source), source_sha=source_sha, checkout=str(root),
                                  baseline_sha=baseline, remote_base_sha=git(root, 'rev-parse', 'origin/release'),
                                  before=before, after=after,
                                  branch=f'release-candidate-{args.version}-{source_sha[:12]}')
                changelog = (frozen / 'CHANGELOG.md').read_text()
                match = re.search(r'^## ' + re.escape(args.version) + r'[^\n]*\n(.*?)(?=^## |\Z)', changelog, re.M | re.S)
                if not match:
                    raise ReleaseError('Add this version to the committed CHANGELOG.md first')
                self.state['notes'] = match.group(1).strip()
                self.save()  # Save the recovery plan before writing the publication checkout.
        self.apply_plan()
        print('Prepared allowlisted files. Review git diff in the publication checkout, then run submit.')

    def validate_plan(self, partial=False):
        root = self.root
        self.require('after', 'before', 'baseline_sha')
        changed = set(git(root, 'diff', '--name-only', self.state['baseline_sha']).splitlines())
        staged = set(git(root, 'diff', '--cached', '--name-only').splitlines())
        committed = set(git(root, 'diff', '--name-only', self.state['baseline_sha'], 'HEAD').splitlines())
        dirty = set(git(root, 'diff', '--name-only', 'HEAD').splitlines())
        if (changed | staged | committed | dirty) - set(self.state['after']):
            raise ReleaseError('Changes outside the release allowlist need review')
        for name, expected in self.state['after'].items():
            current = digest(destination(root, name))
            allowed = {expected, self.state['before'][name]} if partial else {expected}
            if current not in allowed:
                raise ReleaseError(f'Prepared content changed outside the saved plan: {name}')
        return root

    def apply_plan(self):
        root = self.validate_plan(partial=True)
        source = checkout(self.state['source'], 'main')
        with snapshot(source, self.state['source_sha']) as frozen, tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / 'layout'
            paths = layout(frozen, stage)
            generated = {p: digest(stage / p) for p in paths}
            expected = {p: h for p, h in self.state['after'].items() if h is not None}
            if generated != expected:
                raise ReleaseError('Preparation rules changed; resume with the matching tool version')
            for name, expected_hash in self.state['after'].items():
                target = destination(root, name)
                if expected_hash is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(stage / name, target)
        self.validate_plan()
        git(root, 'diff', '--check')
        self.state['prepared'] = True
        self.save()

    def validate_tree(self, sha):
        root = self.root
        for name, expected in self.state['after'].items():
            entry = git(root, 'ls-tree', sha, '--', name)
            if expected is None:
                if entry:
                    raise ReleaseError('Retired file remains in commit: ' + name)
                continue
            if not entry.startswith(('100644 blob ', '100755 blob ')):
                raise ReleaseError('Expected a regular committed release file: ' + name)
            content = subprocess.check_output(['git', 'show', f'{sha}:{name}'], cwd=root)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ReleaseError('Committed release content differs from plan: ' + name)

    def public_notes(self, suffix=''):
        text = re.sub(r'(?m)^\*Last modified: [^\n]+\*\s*$', '', self.state['notes']).rstrip()
        stamp = datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S')
        return text + ('\n\n' + suffix if suffix else '') + f'\n\n*Last modified: {stamp}*\n'

    def submit(self):
        root = self.validate_plan()
        if self.state.get('candidate_sha'):
            if git(root, 'rev-parse', 'HEAD') != self.state['publication_head']:
                raise ReleaseError('Publication HEAD moved after submission')
        else:
            git(root, 'add', '--', *self.state['after'])
            git(root, 'diff', '--cached', '--check')
            if git(root, 'diff', '--cached', '--name-only'):
                git(root, 'commit', '-m', f'Prepare SSHScript {self.state["version"]}')
            clean(root)
            head = git(root, 'rev-parse', 'HEAD')
            self.validate_plan()
            self.validate_tree(head)
            self.state['publication_head'] = head
            # Publish only the reviewed tree on the frozen remote base, never
            # unrelated pre-existing local commit history.
            tree = git(root, 'rev-parse', 'HEAD^{tree}')
            signing = subprocess.run(['git', 'config', '--bool', 'commit.gpgsign'], cwd=root, text=True, capture_output=True)
            flags = ['-S'] if signing.stdout.strip() == 'true' else []
            self.state['candidate_sha'] = git(root, 'commit-tree', *flags, tree, '-p', self.state['remote_base_sha'],
                                              '-m', f'Prepare SSHScript {self.state["version"]}')
            self.save()
        clean(root)
        self.validate_tree(self.state['candidate_sha'])
        branch, sha = self.state['branch'], self.state['candidate_sha']
        existing = git(root, 'ls-remote', 'origin', f'refs/heads/{branch}')
        if existing and existing.split()[0] != sha:
            raise ReleaseError('Remote candidate branch differs; no force push is allowed')
        git(root, 'push', 'origin', f'{sha}:refs/heads/{branch}')
        prs = gh('pr', 'list', '--repo', self.repo, '--base', 'release', '--head', branch,
                 '--state', 'all', '--json', 'number,url,state,headRefOid')
        if prs:
            if len(prs) != 1 or prs[0]['headRefOid'] != sha or prs[0]['state'] == 'CLOSED':
                raise ReleaseError('Existing PR does not match this release')
            pr = prs[0]
        else:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md') as body:
                body.write(self.public_notes('Full required CI must pass before merge.'))
                body.flush()
                run('gh', 'pr', 'create', '--repo', self.repo, '--base', 'release', '--head', branch,
                    '--title', f'SSHScript {self.state["version"]}', '--body-file', body.name)
            prs = gh('pr', 'list', '--repo', self.repo, '--base', 'release', '--head', branch,
                     '--state', 'all', '--json', 'number,url,state,headRefOid')
            if len(prs) != 1 or prs[0]['headRefOid'] != sha:
                raise ReleaseError('Cannot identify the created PR; rerun submit to recover')
            pr = prs[0]
        self.state['pr'] = pr['number']
        self.save()
        print(pr['url'])

    def pr(self):
        self.require('pr', 'candidate_sha')
        pr = gh('pr', 'view', str(self.state['pr']), '--repo', self.repo, '--json',
                'state,headRefOid,baseRefName,mergeCommit,statusCheckRollup,url')
        if pr['headRefOid'] != self.state['candidate_sha'] or pr['baseRefName'] != 'release':
            raise ReleaseError('PR head/base changed; review it before continuing')
        if pr['state'] not in ('OPEN', 'MERGED'):
            raise ReleaseError('PR is closed without merging')
        return pr

    def workflow_run(self, workflow, sha, branch, event):
        runs = api(self.repo, f'actions/workflows/{workflow}/runs?head_sha={sha}&event={event}&per_page=100')['workflow_runs']
        matches = [r for r in runs if r['head_sha'] == sha and r['head_branch'] == branch and r['event'] == event]
        return max(matches, key=lambda r: r['id']) if matches else None

    def ci_once(self):
        pr = self.pr()
        pending, failed = classify_checks(pr['statusCheckRollup'])
        job = self.workflow_run('ci.yml', self.state['candidate_sha'], self.state['branch'], 'pull_request')
        if failed:
            raise ReleaseError('CI failed/skipped/cancelled: ' + ', '.join(failed) + '\n' + pr['url'])
        if job and job['status'] == 'completed' and job['conclusion'] != 'success':
            raise ReleaseError(f'CI run {job["id"]} failed; inspect with gh run view {job["id"]} --repo {self.repo} --log-failed')
        done = not pending and job is not None and job['status'] == 'completed' and job['conclusion'] == 'success'
        return done, f'CI: {len(pr["statusCheckRollup"])-len(pending)} passed, {len(pending)} pending; workflow {job["status"] if job else "not started"}'

    def merge_tag(self):
        root = self.root
        clean(root)
        pr = self.pr()
        if pr['state'] != 'MERGED':
            if not self.ci_once()[0]:
                raise ReleaseError('CI is pending; run wait-ci first')
            run('gh', 'pr', 'merge', str(self.state['pr']), '--repo', self.repo, '--squash',
                '--match-head-commit', self.state['candidate_sha'])
            pr = self.pr()
        sha = pr['mergeCommit']['oid']
        self.state['merge_sha'] = sha
        self.save()
        git(root, 'fetch', 'origin', 'release')
        if git(root, 'rev-parse', sha + '^{tree}') != git(root, 'rev-parse', self.state['candidate_sha'] + '^{tree}'):
            raise ReleaseError('Merged tree differs from the tested candidate; tag not created')
        if version_text(git(root, 'show', sha + ':src/sshscript/_version.py')) != self.state['version']:
            raise ReleaseError('Merged version mismatch')
        tag = 'v' + self.state['version']
        remote = dict((line.split()[1], line.split()[0]) for line in git(root, 'ls-remote', 'origin', f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}').splitlines())
        if remote:
            if remote.get(f'refs/tags/{tag}^{{}}') != sha:
                raise ReleaseError('Remote tag differs or is lightweight; tags are never replaced')
        else:
            if git(root, 'rev-parse', 'FETCH_HEAD') != sha:
                raise ReleaseError('release advanced beyond this merge; refusing to create an older tag')
            local = subprocess.run(['git', 'show-ref', '--verify', '--quiet', f'refs/tags/{tag}'], cwd=root)
            if local.returncode == 1:
                git(root, 'tag', '-a', tag, sha, '-m', f'SSHScript {self.state["version"]}')
            elif local.returncode != 0:
                raise ReleaseError('Cannot inspect the local tag')
            if git(root, 'cat-file', '-t', f'refs/tags/{tag}') != 'tag' or git(root, 'rev-parse', tag + '^{}') != sha:
                raise ReleaseError('Local tag does not match; it will not be replaced')
            git(root, 'push', 'origin', f'refs/tags/{tag}')
        self.state['tag'] = tag
        self.save()
        print(f'{tag} -> {sha}; release workflow triggered')

    def tag_guard(self):
        self.require('tag', 'merge_sha')
        ref = api(self.repo, f'git/ref/tags/{self.state["tag"]}')
        if ref['object']['type'] != 'tag':
            raise ReleaseError('Expected the annotated release tag')
        tag = api(self.repo, f'git/tags/{ref["object"]["sha"]}')
        if tag['object']['type'] != 'commit' or tag['object']['sha'] != self.state['merge_sha']:
            raise ReleaseError('Remote tag moved away from the verified merge commit')

    def release_run(self):
        self.tag_guard()
        job = self.workflow_run('release.yml', self.state['merge_sha'], self.state['tag'], 'push')
        if job:
            self.state['run_id'] = job['id']
            self.save()
        return job

    def assets(self):
        self.require('tag')
        release = gh('release', 'view', self.state['tag'], '--repo', self.repo, '--json', 'isDraft,tagName,url')
        if release['tagName'] != self.state['tag']:
            raise ReleaseError('Release tag mismatch')
        folder = self.path.parent / (self.path.stem + '-artifacts')
        folder.mkdir(parents=True, exist_ok=True)
        run('gh', 'release', 'download', self.state['tag'], '--repo', self.repo, '--dir', folder, '--clobber',
            '--pattern', 'verified.json', '--pattern', '*.whl', '--pattern', '*.tar.gz')
        manifest = json.loads((folder / 'verified.json').read_text())
        version = self.state['version']
        expected = {f'sshscript-{version}-py3-none-any.whl', f'sshscript-{version}.tar.gz'}
        if set(manifest) != expected:
            raise ReleaseError('Expected exactly the selected version wheel and sdist')
        for name, value in manifest.items():
            if digest(folder / name) != value:
                raise ReleaseError('Artifact hash mismatch: ' + name)
        with zipfile.ZipFile(folder / f'sshscript-{version}-py3-none-any.whl') as wheel:
            name = f'sshscript-{version}.dist-info/METADATA'
            if wheel.getinfo(name).file_size > 1_000_000:
                raise ReleaseError('Unexpectedly large wheel metadata')
            metadata = email.message_from_bytes(wheel.read(name))
            if metadata['Name'] != 'sshscript' or metadata['Version'] != version:
                raise ReleaseError('Wheel metadata does not match this release')
        return release, folder, manifest

    def approve(self):
        job = self.release_run()
        if not job:
            raise ReleaseError('Release workflow has not appeared; run wait-release')
        pending = api(self.repo, f'actions/runs/{job["id"]}/pending_deployments')
        if not pending:
            print('No pending environment approval; publication may already be running or complete')
            return
        if len(pending) != 1 or pending[0]['environment']['name'] != 'pypi' or not pending[0]['current_user_can_approve']:
            raise ReleaseError('Expected one pypi deployment that this account may approve')
        latest, page = {}, 1
        while True:
            jobs = api(self.repo, f'actions/runs/{job["id"]}/jobs?filter=all&per_page=100&page={page}')['jobs']
            for item in jobs:
                name = item['name']
                if name not in latest or item.get('id', 0) > latest[name].get('id', 0):
                    latest[name] = item
            if len(jobs) < 100:
                break
            page += 1
        completed = {j['name']: j['conclusion'] for j in latest.values() if j['status'] == 'completed'}
        if (completed.get('Verify and attest release artifacts') != 'success'
                or completed.get('Create draft GitHub Release') != 'success'
                or any(value != 'success' for value in completed.values())):
            raise ReleaseError('Release verification/draft gates have not succeeded')
        release, _, _ = self.assets()
        if not release['isDraft']:
            raise ReleaseError('Expected a verified draft before PyPI approval')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md') as notes:
            notes.write(self.public_notes())
            notes.flush()
            run('gh', 'release', 'edit', self.state['tag'], '--repo', self.repo, '--notes-file', notes.name)
        with tempfile.NamedTemporaryFile(mode='w') as body:
            json.dump(dict(environment_ids=[pending[0]['environment']['id']], state='approved',
                           comment=f'Operator approved SSHScript {self.state["version"]}; release gates and artifact hashes verified.'), body)
            body.flush()
            run('gh', 'api', '--method', 'POST', f'repos/{self.repo}/actions/runs/{job["id"]}/pending_deployments', '--input', body.name)
        print('PyPI environment approved')

    def release_once(self, approve=False):
        job = self.release_run()
        if not job:
            return False, 'Waiting for the tag workflow to appear'
        if job['status'] == 'completed':
            if job['conclusion'] != 'success':
                raise ReleaseError(f'Release run {job["id"]} failed; inspect gh run view {job["id"]} --repo {self.repo} --log-failed')
            return True, f'Release workflow succeeded: {job["html_url"]}'
        pending = api(self.repo, f'actions/runs/{job["id"]}/pending_deployments')
        if pending:
            if not approve:
                raise ApprovalNeeded('PyPI approval is waiting. Run approve-pypi --yes, then wait-release; or finish --publish --approve-pypi.')
            self.approve()
        return False, f'Release workflow: {job["status"]}; {job["html_url"]}'

    def verify(self, install=False):
        if not self.release_once()[0]:
            raise ReleaseError('Release workflow is not complete')
        release, folder, manifest = self.assets()
        if release['isDraft']:
            raise ReleaseError('GitHub Release is still a draft')
        with urllib.request.urlopen(f'https://pypi.org/pypi/sshscript/{self.state["version"]}/json', timeout=30) as response:
            metadata = json.load(response)
        files = {f['filename']: f for f in metadata['urls']}
        if metadata['info']['version'] != self.state['version'] or set(files) != set(manifest):
            raise ReleaseError('PyPI version/distribution list mismatch')
        public = folder / 'pypi'
        public.mkdir(exist_ok=True)
        for name, value in manifest.items():
            item = files[name]
            if item['digests']['sha256'] != value or item['yanked']:
                raise ReleaseError('PyPI hash mismatch or yanked file: ' + name)
            if not item['url'].startswith('https://files.pythonhosted.org/'):
                raise ReleaseError('Unexpected PyPI distribution URL')
            with urllib.request.urlopen(item['url'], timeout=60) as response:
                content = response.read()
            if hashlib.sha256(content).hexdigest() != value:
                raise ReleaseError('Public download hash mismatch: ' + name)
            (public / name).write_bytes(content)
        (folder / 'pypi-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        if install:
            self.install_check(public, folder)
        self.state['verified'] = True
        self.state['install_verified'] = self.state.get('install_verified', False) or install
        self.save()
        print(f'Published SSHScript {self.state["version"]}: {release["url"]}; PyPI hashes verified')

    def install_check(self, public, evidence):
        with tempfile.TemporaryDirectory(prefix='sshscript-published-install-') as tmp:
            env = Path(tmp) / 'venv'
            venv.EnvBuilder(with_pip=True, symlinks=True).create(env)
            python = env / 'bin/python'
            wheel = public / f'sshscript-{self.state["version"]}-py3-none-any.whl'
            run(python, '-I', '-m', 'pip', '--isolated', 'install', '--no-cache-dir', '--index-url', 'https://pypi.org/simple', wheel, cwd=tmp, capture=False)
            run(python, '-I', '-m', 'pip', 'check', cwd=tmp, capture=False)
            if run(env / 'bin/sshscript', '--version', cwd=tmp) != self.state['version']:
                raise ReleaseError('Installed CLI version mismatch')
            script = '''import sys, importlib.metadata as m
from pathlib import Path
import sshscript
assert sshscript.__version__ == m.version('sshscript') == sys.argv[1]
assert Path(sshscript.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
s = sshscript.Session()
try:
 r = s.exec_command([sys.executable, '-c', "print('published-ok')"], command_timeout=5, check=True)
 assert r.stdout.strip() == 'published-ok' and r.exitcode == 0
finally:
 s.close(strict=True)
print('Published installation and strict cleanup passed')
'''
            run(python, '-I', '-c', script, self.state['version'], cwd=tmp, capture=False)
            (evidence / 'installed-requirements.txt').write_text(run(python, '-I', '-m', 'pip', 'freeze', cwd=tmp) + '\n')

    def recover(self, args):
        if self.state:
            raise ReleaseError('Recovery needs a new state path; existing state is never replaced')
        if not VERSION.fullmatch(args.version) or not REPO.fullmatch(args.repo) or args.pr < 1:
            raise ReleaseError('Use a stable version, owner/repository and positive merged PR number')
        root = checkout(args.checkout, 'release', args.repo)
        clean(root)
        pr = gh('pr', 'view', str(args.pr), '--repo', args.repo, '--json',
                'state,headRefOid,headRefName,baseRefName,mergeCommit,url')
        if pr['state'] != 'MERGED' or pr['baseRefName'] != 'release':
            raise ReleaseError('Recover only a PR already merged into release')
        sha = pr['mergeCommit']['oid']
        git(root, 'fetch', 'origin', 'release')
        git(root, 'fetch', 'origin', f'refs/pull/{args.pr}/head')
        if git(root, 'rev-parse', 'FETCH_HEAD') != pr['headRefOid']:
            raise ReleaseError('Fetched PR head does not match GitHub')
        if version_text(git(root, 'show', sha + ':src/sshscript/_version.py')) != args.version:
            raise ReleaseError('Selected version differs from the merged PR')
        if git(root, 'rev-parse', sha + '^{tree}') != git(root, 'rev-parse', pr['headRefOid'] + '^{tree}'):
            raise ReleaseError('Merged tree differs from the PR candidate')
        changelog = git(root, 'show', sha + ':CHANGELOG.md')
        match = re.search(r'^## ' + re.escape(args.version) + r'[^\n]*\n(.*?)(?=^## |\Z)', changelog, re.M | re.S)
        if not match:
            raise ReleaseError('Merged changelog has no matching version entry')
        self.state = dict(schema_version=1, version=args.version, repo=args.repo, checkout=str(root),
                          candidate_sha=pr['headRefOid'], branch=pr['headRefName'], pr=args.pr,
                          merge_sha=sha, notes=match.group(1).strip(), recovered=True)
        tag = 'v' + args.version
        refs = dict((line.split()[1], line.split()[0]) for line in git(root, 'ls-remote', 'origin',
                    f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}').splitlines())
        if refs:
            if refs.get(f'refs/tags/{tag}^{{}}') != sha:
                raise ReleaseError('Existing remote tag does not match this merged PR')
            self.state['tag'] = tag
        self.save()
        print('Recovered the merged PR. Use status, then finish --publish or the individual steps.')

    def status(self):
        if not self.state:
            print('No release state yet. Run prepare or recover.')
            return
        print(json.dumps({k: self.state[k] for k in ('version','source_sha','candidate_sha','pr','merge_sha','tag','run_id','verified','install_verified') if k in self.state}, indent=2))
        if 'pr' in self.state:
            pr = self.pr()
            print(pr['url'], pr['state'])
            print('Checks:', classify_checks(pr['statusCheckRollup']))
        if 'tag' in self.state:
            job = self.workflow_run('release.yml', self.state['merge_sha'], self.state['tag'], 'push')
            if job:
                print(job['html_url'], job['status'], job['conclusion'])


class ApprovalNeeded(ReleaseError):
    pass


class DocsManager(Manager):
    """Selected Markdown only; independent state and no main/tag/package stages."""

    def prepare_docs(self, args):
        if self.state:
            raise ReleaseError('Use a new --state path for each documentation update')
        if not REPO.fullmatch(args.repo):
            raise ReleaseError('Use owner/repository')
        if not args.message.strip() or '\n' in args.message or '\r' in args.message:
            raise ReleaseError('Use a nonempty, single-line commit message')
        source = checkout(args.source, 'working_branch')
        root = checkout(args.checkout, 'release', args.repo)
        if source == root:
            raise ReleaseError('Source and publication checkouts must differ')
        if git(source, 'diff', '--cached', '--name-only'):
            raise ReleaseError('Review and clear staged source changes first')
        # Read only the literal allowlist; never execute a modified preparation tool.
        syntax = ast.parse((source / 'tools/prepare_release.py').read_text())
        allowed = next((ast.literal_eval(n.value) for n in syntax.body
                       if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name)
                       and t.id == 'ROOT_FILES' for t in n.targets)), None)
        if not isinstance(allowed, list) or not all(isinstance(name, str) for name in allowed):
            raise ReleaseError('Missing literal public document allowlist')
        paths = sorted(set(args.files))
        for name in paths:
            if name not in allowed or not name.endswith('.md'):
                raise ReleaseError('Not an allowlisted Markdown document: ' + name)
            path = destination(source, name)
            if not path.is_file():
                raise ReleaseError('Select existing regular documents; deletions are unsupported: ' + name)
            if path.stat().st_mode & 0o111:
                raise ReleaseError('Expected a non-executable regular document: ' + name)
            path.read_bytes().decode('utf-8')
        git(root, 'fetch', 'origin', 'release')
        base = git(root, 'rev-parse', 'refs/remotes/origin/release')
        # Refuse overwriting a document changed upstream since the source copy.
        for name in paths:
            old = git(source, 'ls-tree', 'HEAD', '--', name)
            remote = git(root, 'ls-tree', base, '--', name)
            if old and not old.startswith('100644 blob '):
                raise ReleaseError('Expected a non-executable regular document: ' + name)
            if remote and not remote.startswith('100644 blob '):
                raise ReleaseError('Expected a regular remote document: ' + name)
            old_text = subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=source).decode('utf-8') if old else None
            remote_text = subprocess.check_output(['git', 'show', base + ':' + name], cwd=root).decode('utf-8') if remote else None
            if old_text is not None:
                old_text = old_text.replace('](unittest/', '](src/sshscript/unittest/')
            current = destination(source, name).read_bytes().decode('utf-8').replace('](unittest/', '](src/sshscript/unittest/')
            if remote_text not in (old_text, current):
                raise ReleaseError('Source document differs from remote base; reconcile first: ' + name)
        self.state = dict(schema_version=1, mode='docs', repo=args.repo,
                          source=str(source), checkout=str(root), remote_base_sha=base,
                          source_sha=git(source, 'rev-parse', 'HEAD'),
                          message=args.message, after={name: digest(destination(source, name)) for name in paths})
        tree = self.docs_tree()
        if tree == git(root, 'rev-parse', base + '^{tree}'):
            self.state = {}
            raise ReleaseError('Selected documents already match remote release')
        self.state['docs_tree'] = tree
        self.state['branch'] = 'docs/update-' + tree[:16]
        self.save()
        print(git(root, 'diff', base, tree, '--', *paths))
        print('Plan saved. Review the complete diff above; run docs-finish --push to commit, push, wait and merge.')
        print('Existing GitHub required checks still apply. No version, tag or PyPI publication.')

    def docs_tree(self):
        source = checkout(self.state['source'], 'working_branch')
        root = self.root
        with tempfile.TemporaryDirectory(prefix='sshscript-docs-index-') as folder:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / 'index'))
            def index(*args, data=None):
                result = subprocess.run(['git', *args], cwd=root, env=env, input=data,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode:
                    raise ReleaseError(result.stderr.decode(errors='replace'))
                return result.stdout.decode().strip()
            index('read-tree', self.state['remote_base_sha'])
            for name, expected in self.state['after'].items():
                path = destination(source, name)
                if path.stat().st_mode & 0o111:
                    raise ReleaseError('Expected a non-executable regular document: ' + name)
                content = path.read_bytes()
                if hashlib.sha256(content).hexdigest() != expected:
                    raise ReleaseError('Document changed after planning: ' + name)
                content = content.decode('utf-8').replace('](unittest/', '](src/sshscript/unittest/').encode('utf-8')
                blob = index('hash-object', '-w', '--stdin', data=content)
                index('update-index', '--add', '--cacheinfo', '100644', blob, name)
            tree = index('write-tree')
            index('diff', '--cached', '--check', self.state['remote_base_sha'])
            return tree

    def finish_docs(self):
        self.require('docs_tree', 'after', 'source_sha')
        root = self.root
        if self.docs_tree() != self.state['docs_tree']:
            raise ReleaseError('Document plan changed')
        source = checkout(self.state['source'], 'working_branch')
        staged = set(git(source, 'diff', '--cached', '--name-only').splitlines())
        if staged - set(self.state['after']):
            raise ReleaseError('Review and clear unrelated staged source changes first')
        head = git(source, 'rev-parse', 'HEAD')
        expected = self.state.get('source_commit', self.state['source_sha'])
        if head != expected:
            # Recover a local commit whose response/state save was interrupted.
            changed = set(git(source, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines())
            if (self.state.get('source_commit') or git(source, 'rev-parse', 'HEAD^') != expected
                    or not changed or changed - set(self.state['after'])
                    or git(source, 'diff', 'HEAD', '--', *self.state['after'])):
                raise ReleaseError('Source HEAD moved outside the saved document plan')
        if git(source, 'diff', 'HEAD', '--', *self.state['after']) or any(
                not git(source, 'ls-files', '--', name) for name in self.state['after']):
            git(source, 'add', '--', *self.state['after'])
            git(source, 'commit', '--only', '-m', self.state['message'], '--', *self.state['after'])
        self.state['source_commit'] = git(source, 'rev-parse', 'HEAD')
        if self.docs_tree() != self.state['docs_tree'] or git(source, 'diff', 'HEAD', '--', *self.state['after']):
            raise ReleaseError('Committed source differs from the document plan')
        changes = set(git(source, 'diff', '--name-only', self.state['source_sha'], 'HEAD').splitlines())
        if changes - set(self.state['after']):
            raise ReleaseError('Source commit includes changes outside the document plan')
        self.save()
        if not self.state.get('candidate_sha'):
            signing = subprocess.run(['git', 'config', '--bool', 'commit.gpgsign'], cwd=root, text=True, capture_output=True)
            flags = ['-S'] if signing.stdout.strip() == 'true' else []
            self.state['candidate_sha'] = git(root, 'commit-tree', *flags, self.state['docs_tree'],
                                              '-p', self.state['remote_base_sha'], '-m', self.state['message'])
            self.save()
        sha, branch = self.state['candidate_sha'], self.state['branch']
        existing = git(root, 'ls-remote', 'origin', 'refs/heads/' + branch)
        if existing and existing.split()[0] != sha:
            raise ReleaseError('Remote documentation branch differs; no force push is allowed')
        git(root, 'push', 'origin', sha + ':refs/heads/' + branch)
        prs = gh('pr', 'list', '--repo', self.repo, '--base', 'release', '--head', branch,
                 '--state', 'all', '--json', 'number,url,state,headRefOid')
        if not prs:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md') as body:
                body.write('Update only these documents: ' + ', '.join(self.state['after'])
                           + '\n\nNo version, tag or package publication. Existing required checks apply.\n'
                           + '\n*Last modified: ' + datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S') + '*\n')
                body.flush()
                run('gh', 'pr', 'create', '--repo', self.repo, '--base', 'release', '--head', branch,
                    '--title', self.state['message'], '--body-file', body.name)
            prs = gh('pr', 'list', '--repo', self.repo, '--base', 'release', '--head', branch,
                     '--state', 'all', '--json', 'number,url,state,headRefOid')
        if len(prs) != 1 or prs[0]['headRefOid'] != sha or prs[0]['state'] == 'CLOSED':
            raise ReleaseError('Existing documentation PR does not match the plan')
        self.state['pr'] = prs[0]['number']
        self.save()
        print(prs[0]['url'], flush=True)
        pr = self.pr()
        if pr['state'] != 'MERGED':
            self.poll(self.ci_once)
            run('gh', 'pr', 'merge', str(self.state['pr']), '--repo', self.repo, '--squash',
                '--match-head-commit', sha)
            pr = self.pr()
        if pr['state'] != 'MERGED':
            raise ReleaseError('Documentation PR merge is not confirmed')
        merged = pr['mergeCommit']['oid']
        git(root, 'fetch', 'origin', merged)
        changed = set(git(root, 'diff-tree', '--no-commit-id', '--name-only', '-r', merged).splitlines())
        if changed - set(self.state['after']):
            raise ReleaseError('Merged commit contains changes outside the documentation plan')
        for name in self.state['after']:
            if git(root, 'rev-parse', merged + ':' + name) != git(root, 'rev-parse', sha + ':' + name):
                raise ReleaseError('Merged document differs from the reviewed plan: ' + name)
        self.state['merge_sha'] = merged
        self.save()
        print('Documentation merged: ' + merged)
        print('src/main and the publication worktree were not changed. No tag or package was published.')


def main(argv=None):
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, help='Saved workflow state; use a separate path per update')
    parser.add_argument('--interval', type=int, default=60, help='CI polling seconds (default: 60)')
    parser.add_argument('--timeout', type=int, default=0, help='Wait limit in seconds; 0 means until stopped')
    commands = parser.add_subparsers(dest='command', required=True)
    docs = commands.add_parser('docs-prepare', help='Plan selected working_branch Markdown files without publishing')
    docs.add_argument('--source', type=Path, required=True)
    docs.add_argument('--checkout', type=Path, required=True)
    docs.add_argument('--repo', default='iapyeh/sshscript')
    docs.add_argument('--message', required=True)
    docs.add_argument('--files', nargs='+', required=True)
    docs_finish = commands.add_parser('docs-finish', help='Commit selected docs, push PR, wait for checks and merge; no tag/PyPI')
    docs_finish.add_argument('--push', action='store_true', required=True)
    prep = commands.add_parser('prepare', help='Read committed main and sync only allowlisted release inputs')
    prep.add_argument('--version', required=True)
    prep.add_argument('--source', type=Path, required=True)
    prep.add_argument('--checkout', type=Path, required=True)
    prep.add_argument('--repo', default='iapyeh/sshscript')
    prep.add_argument('--remove-retired', action='store_true', help='Explicitly remove retired, previously public inputs')
    recover = commands.add_parser('recover', help='Resume an already merged PR, including an existing tag/workflow')
    recover.add_argument('--version', required=True)
    recover.add_argument('--pr', type=int, required=True)
    recover.add_argument('--checkout', type=Path, required=True)
    recover.add_argument('--repo', default='iapyeh/sshscript')
    for name in ('submit','wait-ci','merge-tag','wait-release','status'):
        commands.add_parser(name)
    approve = commands.add_parser('approve-pypi', help='Verify assets and approve the protected PyPI environment')
    approve.add_argument('--yes', action='store_true', required=True)
    verify = commands.add_parser('verify')
    verify.add_argument('--install-check', action='store_true')
    finish = commands.add_parser('finish', help='Submit, wait, merge/tag, publish and verify; safely resume the saved release')
    finish.add_argument('--publish', action='store_true', required=True)
    finish.add_argument('--approve-pypi', action='store_true', help='Explicitly approve pypi after gate/hash verification')
    args = parser.parse_args(argv)
    if args.interval < 1 or args.timeout < 0:
        parser.error('interval must be positive and timeout nonnegative')
    try:
        docs_mode = args.command.startswith('docs-')
        if args.state is None:
            variable = 'SSHSCRIPT_DOCS_STATE' if docs_mode else 'SSHSCRIPT_RELEASE_STATE'
            filename = 'docs.json' if docs_mode else 'release.json'
            args.state = Path(os.environ.get(variable, '~/.local/state/sshscript/' + filename))
        manager = (DocsManager if docs_mode else Manager)(args.state, args.interval, args.timeout)
        if manager.state and (manager.state.get('mode') == 'docs') != docs_mode:
            raise ReleaseError('State belongs to a different workflow; use a separate --state path')
        if docs_mode:
            with manager.lock():
                if args.command == 'docs-prepare': manager.prepare_docs(args)
                else: manager.finish_docs()
            return 0
        if args.command == 'status':
            manager.status()
            return 0
        with manager.lock():
            if args.command == 'prepare': manager.prepare(args)
            elif args.command == 'recover': manager.recover(args)
            elif args.command == 'submit': manager.submit()
            elif args.command == 'wait-ci': manager.poll(manager.ci_once)
            elif args.command == 'merge-tag': manager.merge_tag()
            elif args.command == 'wait-release': manager.poll(manager.release_once)
            elif args.command == 'approve-pypi': manager.approve()
            elif args.command == 'verify': manager.verify(args.install_check)
            elif args.command == 'finish':
                if not manager.state.get('pr'): manager.submit()
                if not manager.state.get('tag'):
                    manager.poll(manager.ci_once)
                    manager.merge_tag()
                manager.poll(lambda: manager.release_once(args.approve_pypi))
                manager.verify(install=True)
        return 0
    except ApprovalNeeded as error:
        print(str(error), file=sys.stderr)
        return 3
    except (ReleaseError, OSError, ValueError, KeyError, zipfile.BadZipFile, tarfile.TarError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Stopped; state retained. Resume the same command.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
