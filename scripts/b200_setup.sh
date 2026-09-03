#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/criteo/prompt_policy_llm}"
VENV_DIR="${VENV_DIR:-${REPO_DIR}/.venv}"

cd "${REPO_DIR}"
python3.12 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip wheel setuptools
python -m pip install --prefer-binary --extra-index-url https://pypi.org/simple -r requirements-b200.txt
python - <<'PY'
import torch
import transformers

print("torch", torch.__version__)
print("transformers", transformers.__version__)
print("cuda_available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("cuda_device", torch.cuda.get_device_name(0))
PY

