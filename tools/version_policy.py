"""Check the explicit production channel without editing package versions."""
import argparse
from pathlib import Path
import runpy
from packaging.version import Version


def require_production_version(value):
    version = Version(str(value))
    if version.is_prerelease or version.local is not None:
        raise ValueError(f'{version} is not a production version; use local validation or TestPyPI')
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', action='store_true', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / 'src/sshscript' if (root / 'src/sshscript').is_dir() else root
    require_production_version(runpy.run_path(str(source / '_version.py'))['__version__'])


if __name__ == '__main__':
    main()
