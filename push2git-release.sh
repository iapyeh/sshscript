#!/bin/sh
set -eu
BASEDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$BASEDIR"
test "$(git branch --show-current)" = release
if test "$#" -ne 1; then
    echo 'Usage: sh push2git-release.sh "commit message"' >&2
    exit 2
fi
# Review staged files before invoking this explicit commit/push entry point.
git diff --cached --check
if git diff --cached --quiet; then
    echo 'Stage the reviewed release files explicitly, including new files, first.' >&2
    exit 2
fi
git commit -m "$1"
git push origin release
