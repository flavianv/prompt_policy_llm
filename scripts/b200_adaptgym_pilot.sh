#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/criteo/qwen17b-work
export PYTHONPATH="$ROOT/prompt_policy_llm/src:$ROOT/adaptgym/src"
export HF_HOME="$ROOT/hf-cache"
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1
export CUDA_VISIBLE_DEVICES=0
exec /home/criteo/verl-venv/bin/python -m prompt_policy_llm.adaptgym_pilot "$@"
