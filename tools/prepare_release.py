"""Prepare the allowlisted release layout without committing or publishing."""
import argparse
import shutil
from pathlib import Path

MODULES = '__init__ _version sshscript session patching errorutils tokenparser dollarparser dollarchanger spyimporter channelssh channelsubprocess channelutils channelgeneric sessionwrapper stdio dollar'.split()
ROOT_FILES = ['pyproject.toml', 'README.md', 'LICENSE.txt', 'RELEASING.md', 'MANIFEST.in', '.github/workflows/ci.yml']
TOOLS = ['prepare_release.py', 'check_release.py', 'run_checks.py', 'publish_release.py']
TESTS = ['check_package_asserts.py', 'dollar_syntax.spy', 'dollar_syntax_fixture.spy', 'language.spy', 'language_fixture.spy', 'test_channelgeneric_expect.py', 'test_file_transfer.py', 'test_logger_api.py', 'test_logger_integration.py', 'test_production_contract.py', 'test_session_close_reporting.py', 'test_session_proxy_cleanup.py', 'test_spy_source_mapping.py', 'test_spy_thread_session.py', 'test_ssh_security.py', 'test_sshscript_dollar_syntax.py', 'test_sshscript_module.py', 'test_stdio_dynamic_string.py', 'test_syntax_error.spy', 'test_update_check.py']

def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents:
        raise ValueError('Destination must be outside the source tree')
    package = source / 'src/sshscript' if (source / 'src/sshscript').is_dir() else source
    pairs = [(source / p, destination / p) for p in ROOT_FILES]
    pairs += [(source / 'tools' / p, destination / 'tools' / p) for p in TOOLS]
    pairs += [(package / (p + '.py'), destination / 'src/sshscript' / (p + '.py')) for p in MODULES]
    pairs += [(package / 'unittest' / p, destination / 'src/sshscript/unittest' / p) for p in TESTS]
    missing = [str(src) for src, _ in pairs if not src.is_file()]
    if missing:
        raise FileNotFoundError('Missing release inputs: ' + ', '.join(missing))
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return [str(dst.relative_to(destination)) for _, dst in pairs]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    for path in prepare(args.source, args.destination):
        print(path)
