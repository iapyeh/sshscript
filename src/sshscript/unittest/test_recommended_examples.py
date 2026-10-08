"""Execute every canonical example, including SSH via a real Paramiko fixture."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import re
from unittest.mock import patch

import unittest
import test_command_job as fixtures
import sshscript


class RecommendedExamplesTests(unittest.TestCase):
    local = fixtures.CommandJobTests.local
    remote = fixtures.CommandJobTests.remote


def test_canonical_examples(self):
    here = Path(__file__).resolve()
    guide = next((p / 'API_GUIDE.md' for p in here.parents if (p / 'API_GUIDE.md').is_file()), None)
    self.assertIsNotNone(guide, 'canonical guide must ship in source distributions')
    text = guide.read_text()
    blocks = re.findall(r'<!-- example: (.+?) -->\n```python\n(.*?)```', text, re.S)
    self.assertEqual(len(blocks), text.count('```python'), 'every example needs a version profile')
    self.assertEqual(len(blocks), 10)
    ids = set()
    for metadata, source in blocks:
        example = json.loads(metadata)
        self.assertNotIn(example['id'], ids)
        ids.add(example['id'])
        self.assertIn(example['profile'], ('3.1.5', sshscript.__version__))
        with self.subTest(example=example['id']):
            output = StringIO()
            with redirect_stdout(output):
                if example.get('fixture') == 'ssh':
                    remote = self.remote()
                    with patch.object(sshscript.Session, 'connect', return_value=remote):
                        sshscript.run_script(source)
                else:
                    sshscript.run_script(source)
            self.assertEqual(output.getvalue(), example['stdout'])

RecommendedExamplesTests.test_canonical_examples = test_canonical_examples


def test_readme_quickstart(self):
    root = next(p for p in Path(__file__).resolve().parents if (p / 'API_GUIDE.md').is_file())
    text = (root / 'README.md').read_text()
    blocks = re.findall(r'<!-- example: (.+?) -->\n```python\n(.*?)```', text, re.S)
    self.assertEqual(len(blocks), 1, 'README quickstart must remain executable')
    for metadata, source in blocks:
        example = json.loads(metadata)
        self.assertEqual(example['profile'], '3.1.5')
        output = StringIO()
        with redirect_stdout(output):
            sshscript.run_script(source)
        self.assertEqual(output.getvalue(), example['stdout'])
    dollar = re.search(r'## Optional dollar syntax.*?```spy\n(.*?)```', text, re.S)
    self.assertIsNotNone(dollar)
    output = StringIO()
    with redirect_stdout(output):
        sshscript.run_script(dollar[1])
    self.assertEqual(output.getvalue(), 'ready\n')


def test_source_document_links_survive_release_staging(self):
    import tempfile
    import sys
    root = next(p for p in Path(__file__).resolve().parents if (p / 'tools/prepare_release.py').is_file())
    sys.path.insert(0, str(root / 'tools'))
    from prepare_release import prepare
    with tempfile.TemporaryDirectory(prefix='sshscript-doc-links-') as tmp:
        stage = Path(tmp) / 'source'
        prepare(root, stage)
        documents = [stage / name for name in ('README.md', 'API_GUIDE.md', 'SECURITY.md', 'CONTRIBUTING.md')]
        documents.extend((stage / 'src/sshscript/unittest').glob('README*.md'))
        for document in documents:
            name = document.relative_to(stage)
            text = document.read_text()
            for target in re.findall(r'\]\(([^)]+)\)', text):
                path = target.split('#', 1)[0]
                if not path or '://' in path:
                    continue
                destination = document.parent / path
                self.assertTrue(destination.is_file(), f'{name}: missing shipped link {target}')

RecommendedExamplesTests.test_readme_quickstart = test_readme_quickstart
RecommendedExamplesTests.test_source_document_links_survive_release_staging = test_source_document_links_survive_release_staging
