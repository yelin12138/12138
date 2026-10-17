#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "$0")"
printf 'MotorLab v0.4.0 - starting this extracted folder: %s\n' "$PWD"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import numpy, matplotlib' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python run_workbench.py --open "$@"
