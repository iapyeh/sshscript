#!/bin/sh
set -eu
BASEDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$BASEDIR/../src/tools/prepare_release.py" --source "$BASEDIR/../src" --destination "$BASEDIR"
