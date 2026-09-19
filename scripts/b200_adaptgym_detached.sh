#!/usr/bin/env bash
set -uo pipefail
ROOT=/home/criteo/qwen17b-work
OUT="$ROOT/runs/adaptgym_10x10_20260917_v2"
"$ROOT/prompt_policy_llm/scripts/b200_adaptgym_pilot.sh" --credentials /home/criteo/reco-rl/app/backend/.env --output "$OUT"
code=$?
printf '%s\n' "$code" > "$ROOT/runs/adaptgym_10x10_20260917_v2.exit"
exit "$code"
