#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
STREETTWIN_PYTHON="${STREETTWIN_PYTHON:-../../.venv/bin/python}"
if [[ ! -x "$STREETTWIN_PYTHON" ]]; then STREETTWIN_PYTHON=python3; fi
exec bash with-runtime.sh "$STREETTWIN_PYTHON" deploy.py
