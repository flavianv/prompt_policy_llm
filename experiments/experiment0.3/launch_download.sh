#!/bin/bash
set -u
BASE=/home/criteo/qwen17b-work/note-rl-20260917
export PYTHONUNBUFFERED=1
/home/criteo/verl-venv/bin/python "$BASE/experiments/experiment0.3/download_model.py"
code=$?
echo "$code" > "$BASE/download.exit"
exit "$code"
