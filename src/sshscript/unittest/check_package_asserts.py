"""Dependency-free gate for the flat shipped package (tests are not packaged)."""
import ast
from pathlib import Path


def violations():
    root = Path(__file__).resolve().parent.parent
    return [f'{path.name}:{node.lineno}'
            for path in sorted(root.glob('*.py'))
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
            if isinstance(node, ast.Assert)]


if __name__ == '__main__':
    failures = violations()
    if failures:
        raise SystemExit('Runtime assertions in package: ' + ', '.join(failures))
    print('Package assert scan passed')
