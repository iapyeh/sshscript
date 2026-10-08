"""Render the canonical guide into a separately checked-out documentation site."""
import argparse
from datetime import datetime
import os
import re
import time
from pathlib import Path

HEADER = '''---
title: "Recommended SSHScript API"
parent: "SSHScript v3.1 Documentation"
nav_order: 0
permalink: /v3a/recommended-api/
---

<!-- Generated from API_GUIDE.md; do not edit this copy. -->

'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    content = HEADER + (Path(__file__).resolve().parents[1] / 'API_GUIDE.md').read_text()
    content = content.replace('(VERSIONING.md)', '({{ site.baseurl }}/v3a/migration-and-releases/version-policy/)')
    if args.check:
        existing = re.sub(r"\nLast Updated: [^\n]+\n?$", "", args.destination.read_text())
        if existing.rstrip() != content.rstrip():
            raise SystemExit('Canonical guide website copy is stale')
    else:
        stamp = int(time.time())
        updated = datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M:%S")
        args.destination.write_text(content.rstrip() + f"\n\nLast Updated: {updated}\n")
        os.utime(args.destination, (stamp, stamp))

if __name__ == '__main__':
    main()
