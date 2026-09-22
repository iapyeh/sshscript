"""Explicitly upload exactly the previously verified artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--artifacts', type=Path, required=True)
parser.add_argument('--repository', choices=['pypi', 'testpypi'], required=True)
args = parser.parse_args()
root = args.artifacts.resolve()
manifest = json.loads((root / 'verified.json').read_text())
if len(manifest) != 2 or sum(name.endswith('.whl') for name in manifest) != 1 or sum(name.endswith('.tar.gz') for name in manifest) != 1:
    raise ValueError('Expected one verified wheel and one verified sdist')
files = []
for name, digest in manifest.items():
    if Path(name).name != name:
        raise ValueError('Invalid artifact name')
    path = root / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Artifact changed after verification: ' + name)
    files.append(str(path))
subprocess.run([sys.executable, '-m', 'twine', 'check', '--strict', *files], check=True)
subprocess.run([sys.executable, '-m', 'twine', 'upload', '--non-interactive', '--repository', args.repository, *files], check=True)
