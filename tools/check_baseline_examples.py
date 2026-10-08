"""Run canonical credential-free stable examples against installed 3.1.5.

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
source = (Path(__file__).resolve().parents[1] / 'API_GUIDE.md').read_text()
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
if count != 3:
    raise RuntimeError('Expected three credential-free baseline examples')
print('Published 3.1.5: all three credential-free canonical examples passed')
