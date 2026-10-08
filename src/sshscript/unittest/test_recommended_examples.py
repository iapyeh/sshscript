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
    self.assertEqual(len(blocks), 9)
    ids = set()
    for metadata, source in blocks:
        example = json.loads(metadata)
        self.assertNotIn(example['id'], ids)
        ids.add(example['id'])
        self.assertIn(example['profile'], ('3.1.5', 'unreleased'))
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
