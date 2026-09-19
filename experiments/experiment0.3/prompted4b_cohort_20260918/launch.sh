#!/bin/bash
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH=/home/criteo/qwen17b-work/prompted4b_cohort_20260918/src
cd /home/criteo/qwen17b-work/prompted4b_cohort_20260918
/home/criteo/verl-venv/bin/python /home/criteo/qwen17b-work/prompted4b_cohort_20260918/run_prompted_cohort.py --root /home/criteo/qwen17b-work/prompted4b_cohort_20260918 --credentials /home/criteo/reco-rl/app/backend/.env
code=$?
echo "$code" > /home/criteo/qwen17b-work/prompted4b_cohort_20260918/job.exit
exit "$code"
