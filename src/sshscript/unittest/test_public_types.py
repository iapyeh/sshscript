"""Keep annotated public methods and shipped PEP 561 files aligned."""
import ast
import inspect
from pathlib import Path
import unittest
from session import Session
from commandjob import CommandJob

class PublicTypeTests(unittest.TestCase):
    def test_public_stub_methods_exist_and_keywords_match(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / 'py.typed').is_file())
        for filename, cls in [('session.pyi', Session), ('commandjob.pyi', CommandJob)]:
            tree = ast.parse((root / filename).read_text())
            definition = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls.__name__)
            for node in definition.body:
                if not isinstance(node, ast.FunctionDef):
                    continue
                implementation = getattr(cls, node.name)
                if isinstance(implementation, property):
                    continue
                signature = inspect.signature(implementation)
                params = signature.parameters
                dynamic = any(p.kind == p.VAR_KEYWORD for p in params.values())
                for argument in node.args.args + node.args.kwonlyargs:
                    self.assertTrue(argument.arg in params or dynamic,
                                    f'{filename}: {node.name}.{argument.arg}')
