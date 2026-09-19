#!/bin/bash
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH=/home/criteo/qwen17b-work/cumulative-temp15-20260918/src
cd /home/criteo/qwen17b-work/cumulative-temp15-20260918
/home/criteo/verl-venv/bin/python -m prompt_policy_llm.train_note_grpo --config /home/criteo/qwen17b-work/cumulative-temp15-20260918/experiments/experiment0.3/structured_all100_config.json --manifest /home/criteo/qwen17b-work/cumulative-temp15-20260918/experiments/experiment0.3/model_manifest.json --data /home/criteo/qwen17b-work/cumulative-temp15-20260918/experiments/experiment0.3/structured_notes_v1 --output /home/criteo/qwen17b-work/cumulative-temp15-20260918/all100_01/run --steps 100
code=$?
echo "$code" > /home/criteo/qwen17b-work/cumulative-temp15-20260918/all100_01/job.exit
exit "$code"
