"""Run canonical guide and README examples against installed 3.1.5.

Run with python -I after installing sshscript==3.1.5. The SSH example uses
an authenticated fixture in test_recommended_examples instead of a real host.
"""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import re
import sshscript

if sshscript.__version__ != '3.1.5':
    raise RuntimeError('This check requires the published 3.1.5 baseline')
root = Path(__file__).resolve().parents[1]
source = '\n'.join((root / name).read_text() for name in ('API_GUIDE.md', 'README.md'))
count = 0
for metadata, code in re.findall(r'<!-- example: (.+?) -->\n```python\n(.*?)```', source, re.S):
    example = json.loads(metadata)
    if example['profile'] != '3.1.5' or example.get('fixture'):
        continue
    output = StringIO()
    with redirect_stdout(output):
        sshscript.run_script(code)
    if output.getvalue() != example['stdout']:
        raise RuntimeError(f'Baseline example failed: {example["id"]}')
    count += 1
if count != 4:
    raise RuntimeError('Expected four credential-free baseline examples')
dollar = re.search(r'## Optional dollar syntax.*?```spy\n(.*?)```', (root / 'README.md').read_text(), re.S)
if dollar is None:
    raise RuntimeError('README Dollar syntax example is missing')
output = StringIO()
with redirect_stdout(output):
    sshscript.run_script(dollar[1])
if output.getvalue() != 'ready\n':
    raise RuntimeError('README Dollar syntax example failed')
print('Published 3.1.5: four guide/README Python examples and README Dollar example passed')
