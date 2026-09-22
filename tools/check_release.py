"""Build and install-check a release in disposable directories. Never publish."""
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
from prepare_release import prepare

def run(*args, cwd, env=None):
    subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True, help='New, non-existing artifact directory')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('Output already exists; choose a new directory')
    with tempfile.TemporaryDirectory(prefix='sshscript-release-') as folder:
        root = Path(folder)
        stage, dist = root / 'source', root / 'dist'
        prepare(args.source, stage)
        run(sys.executable, '-m', 'build', '--outdir', dist, cwd=stage)
        artifacts = sorted(dist.glob('*'))
        if len(list(dist.glob('*.whl'))) != 1 or len(list(dist.glob('*.tar.gz'))) != 1:
            raise RuntimeError('Expected exactly one wheel and one sdist')
        run(sys.executable, '-m', 'twine', 'check', '--strict', *artifacts, cwd=root)
        venv.EnvBuilder(with_pip=True, symlinks=True).create(root / 'venv')
        python = root / 'venv/bin/python'
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        run(python, '-m', 'pip', 'install', next(dist.glob('*.whl')), cwd=root, env=env)
        run(python, '-c', "import importlib.metadata as m; import sshscript; from sshscript import _version; assert sshscript.__version__ == _version.__version__ == m.version('sshscript'); s = sshscript.Session(); out, err = s.exec_command('printf release-smoke'); assert str(out) == 'release-smoke'; s.close(strict=True); print('Installed wheel smoke test passed:', sshscript.__version__)", cwd=root, env=env)
        run(root / 'venv/bin/sshscript', '--help', cwd=root, env=env)
        output.mkdir(parents=True)
        for item in artifacts:
            shutil.copy2(item, output / item.name)
        manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}
        (output / 'verified.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print('Verified artifacts:', output)

if __name__ == '__main__':
    main()
