"""Generate/check the agent guide and downloadable assets in gh-pages/v3a."""
import argparse
from datetime import datetime
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HEADER = '''---
title: "SSHScript Agent Guide"
parent: "SSHScript for AI Agents"
grand_parent: "SSHScript Documentation"
nav_order: 1
permalink: /v3a/ai-agents/guide/
---

<!-- Generated from skills/sshscript/references/agent-guide.md; do not edit. -->

'''


def outputs():
    """Return reproducible content; ZIP timestamps do not depend on the clock."""
    skill = (ROOT / 'skills/sshscript/SKILL.md').read_bytes()
    guide = (ROOT / 'skills/sshscript/references/agent-guide.md').read_bytes()
    api = (ROOT / 'API_GUIDE.md').read_bytes()
    versioning = (ROOT / 'VERSIONING.md').read_bytes()
    # The snapshots travel together; repair their mutual documentation link.
    api = api.replace(b'(VERSIONING.md)', b'(versioning.md)')
    versioning = versioning.replace(b'(API_GUIDE.md#', b'(api-guide.md#')
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in (
            ('sshscript/SKILL.md', skill),
            ('sshscript/references/agent-guide.md', guide),
            ('sshscript/references/api-guide.md', api),
            ('sshscript/references/versioning.md', versioning),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return {
        'ai-agents/guide.md': HEADER.encode() + guide,
        'ai-agents/downloads/agent-guide.txt': guide,
        # A leading YAML fence makes Jekyll render even .txt as a page.
        'ai-agents/downloads/SKILL.txt':
            b'SSHScript skill instructions (use the ZIP for installation)\n\n' + skill,
        'ai-agents/downloads/sshscript-skill.zip': stream.getvalue(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='Existing gh-pages/v3a directory')
    parser.add_argument('--check', action='store_true', help='Check without writing')
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.name != 'v3a' or not destination.is_dir():
        parser.error('Destination must be an existing v3a directory')
    if not args.check:
        branch = subprocess.check_output(
            ['git', 'branch', '--show-current'], cwd=destination, text=True,
        ).strip()
        root = Path(subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'], cwd=destination, text=True,
        ).strip()).resolve()
        if branch != 'gh-pages' or destination.parent != root:
            parser.error('Writes require v3a directly inside a gh-pages branch checkout')
    stale = []
    for relative, content in outputs().items():
        path = destination / relative
        if args.check:
            existing = path.read_bytes() if path.is_file() else b''
            if relative.endswith('.md'):
                existing = re.sub(rb'\nLast Updated: [^\n]+\n?$', b'', existing).rstrip() + b'\n'
            if existing != content:
                stale.append(relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative.endswith('.md'):
                stamp = int(datetime.now().timestamp())
                updated = datetime.fromtimestamp(stamp).strftime('%Y-%m-%d %H:%M:%S')
                path.write_bytes(content.rstrip() + f'\n\nLast Updated: {updated}\n'.encode())
                os.utime(path, (stamp, stamp))
            else:
                path.write_bytes(content)
    if stale:
        raise SystemExit('Stale or missing AI assets: ' + ', '.join(stale))
    print('AI documentation assets ' + ('match source' if args.check else 'synchronized'))


if __name__ == '__main__':
    main()
