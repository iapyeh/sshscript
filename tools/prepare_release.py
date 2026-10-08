"""Prepare the allowlisted release layout without committing or publishing."""
import argparse
import shutil
from pathlib import Path

MODULES = '__init__ _runtime _version sshscript session sessionsettings commandresult commandjob consolejob sshconfig patching errorutils tokenparser dollarparser dollarchanger spyimporter channelssh channelsubprocess channelutils channelgeneric sessionwrapper stdio dollar'.split()
ROOT_FILES = [
    'API_GUIDE.md', 'pyproject.toml', 'README.md', 'LICENSE.txt', 'RELEASING.md',
    'MANIFEST.in', 'CHANGELOG.md', 'CONTRIBUTING.md', 'EXCEPTIONS.md',
    'SECURITY.md', 'SUPPORT.md', 'CODE_OF_CONDUCT.md', '.gitignore',
    '.github/ISSUE_TEMPLATE/bug_report.yml',
    '.github/ISSUE_TEMPLATE/config.yml',
    '.github/ISSUE_TEMPLATE/feature_request.yml',
    '.github/pull_request_template.md', '.github/dependabot.yml',
    '.github/workflows/ci.yml', '.github/workflows/codeql.yml',
    '.github/workflows/release.yml',
]
TOOLS = [
    'check_baseline_examples.py', 'sync_api_guide.py', 'check_public_types.py', 'prepare_release.py', 'check_release.py', 'run_checks.py',
    'publish_release.py', 'setup_openssh_ci.sh', 'run_native_auth_ci.py',
]
# Public regression fixtures and instructions; private legacy tests are excluded.
TESTS = [
    'README.console-authentication.md',
    'README.console-results.md',
    'README.dollar-syntax-tests.md',
    'README.module-tests.md',
    'check_package_asserts.py',
    'dollar_syntax.spy',
    'dollar_syntax_fixture.spy',
    'language_fixture.spy',
    'test_channelgeneric_expect.py',
    'test_check_file.py',
    'test_command_api.py',
    'test_command_job.py',
    'test_console_authentication.py',
    'test_native_console_authentication.py',
    'test_native_auth_runner.py',
    'test_console_results.py',
    'test_console_job.py',
    'test_dollar_command_escapes.py',
    'test_file_transfer.py',
    'test_logger_api.py',
    'test_logger_integration.py',
    'test_openssh_integration.py',
    'test_production_contract.py',
    'test_public_types.py',
    'test_python_version.py',
    'test_release_inputs.py',
    'test_recommended_examples.py',
    'test_session_close_reporting.py',
    'test_session_proxy_cleanup.py',
    'test_session_settings.py',
    'test_spy_source_mapping.py',
    'test_spy_thread_session.py',
    'test_ssh_config.py',
    'test_ssh_security.py',
    'test_sshscript_dollar_syntax.py',
    'test_sshscript_module.py',
    'test_stdio_dynamic_string.py',
    'test_syntax_error.spy',
    'test_update_check.py',
]

def validate_release_inputs(source):
    """Refuse regressions that run locally but disappear from a release."""
    source = Path(source).resolve()
    package = source / 'src/sshscript' if (source / 'src/sshscript').is_dir() else source
    approved = set(TESTS)
    if len(approved) != len(TESTS):
        raise ValueError('Duplicate public test release inputs')
    discovered = {p.name for p in (package / 'unittest').glob('test_*.py')}
    omitted = sorted(discovered - approved)
    if omitted:
        raise ValueError('Regression tests missing from release allowlist: ' + ', '.join(omitted))
    missing = sorted(name for name in approved if not (package / 'unittest' / name).is_file())
    if missing:
        raise FileNotFoundError('Missing public test release inputs: ' + ', '.join(missing))
    manifest = (source / 'MANIFEST.in').read_text().splitlines()
    expected = {'include src/sshscript/unittest/' + name for name in TESTS}
    actual = {line.strip() for line in manifest if 'src/sshscript/unittest' in line}
    if actual != expected:
        raise ValueError('MANIFEST.in public test list differs from release allowlist; '
                         'missing: ' + ', '.join(sorted(expected - actual)) +
                         '; unexpected: ' + ', '.join(sorted(actual - expected)))


def verify_sdist_tests(stage, archive):
    """Require the sdist to retain the approved tests and instructions byte for byte."""
    import tarfile
    stage = Path(stage)
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        roots = {m.name.split('/')[0] for m in members}
        if len(roots) != 1:
            raise ValueError('Expected one sdist root')
        prefix = next(iter(roots)) + '/src/sshscript/unittest/'
        actual = {m.name[len(prefix):] for m in members if m.isfile() and m.name.startswith(prefix)}
        if actual != set(TESTS):
            raise ValueError('sdist public test list differs from release allowlist')
        for name in TESTS:
            member = tar.getmember(prefix + name)
            if not member.isfile():
                raise ValueError('sdist test input is not a regular file: ' + name)
            with tar.extractfile(member) as stream:
                if stream.read() != (stage / 'src/sshscript/unittest' / name).read_bytes():
                    raise ValueError('sdist changed public test input: ' + name)


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents:
        raise ValueError('Destination must be outside the source tree')
    validate_release_inputs(source)
    package = source / 'src/sshscript' if (source / 'src/sshscript').is_dir() else source
    pairs = [(source / p, destination / p) for p in ROOT_FILES]
    pairs += [(source / 'tools' / p, destination / 'tools' / p) for p in TOOLS]
    pairs += [(package / (p + '.py'), destination / 'src/sshscript' / (p + '.py')) for p in MODULES]
    bootstrap = source / 'src/_sshscript_cli.py' if (source / 'src/sshscript').is_dir() else source / '_sshscript_cli.py'
    pairs.append((bootstrap, destination / 'src/_sshscript_cli.py'))
    pairs += [(package / 'unittest' / p, destination / 'src/sshscript/unittest' / p) for p in TESTS]
    pairs += [(package / p, destination / 'src/sshscript' / p) for p in ('py.typed', '__init__.pyi', 'session.pyi', 'sessionwrapper.pyi', 'commandjob.pyi', 'commandresult.pyi')]
    missing = [str(src) for src, _ in pairs if not src.is_file()]
    if missing:
        raise FileNotFoundError('Missing release inputs: ' + ', '.join(missing))
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return [str(dst.relative_to(destination)) for _, dst in pairs]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    for path in prepare(args.source, args.destination):
        print(path)


if __name__ == '__main__':
    main()
