#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/criteo/prompt_policy_llm}"
VENV_DIR="${VENV_DIR:-${REPO_DIR}/.venv}"
TRAIN_FILE="${TRAIN_FILE:-${REPO_DIR}/runs/omni_math_rule/latest/controller_sft_seed.jsonl}"
OUT_DIR="${OUT_DIR:-${REPO_DIR}/models/smollm2_135m_controller_sft}"

cd "${REPO_DIR}"
source "${VENV_DIR}/bin/activate"
python -m prompt_policy_llm.train_controller \
  --train-file "${TRAIN_FILE}" \
  --output-dir "${OUT_DIR}" \
  --bf16

