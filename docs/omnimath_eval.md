# Omni-MATH Rule Eval

This eval compares:

- Zero-shot Luna baseline.
- SmolLM2-135M-Instruct controller plus the same frozen Luna solver.

The controller emits one short steering instruction, capped by `--controller-tokens`, defaulting to 30 generated controller tokens. Luna is separate: it receives the original problem plus the optional controller instruction and uses `--max-output-tokens` as the solver answer budget.

## Setup

Install the lightweight package and API dependency:

```bash
python3 -m pip install -e ".[api]"
```

For the local SmolLM2 controller, install:

```bash
python3 -m pip install -e ".[api,controller]"
```

## Smoke Test

```bash
python3 -m prompt_policy_llm.eval_omnimath --limit 2 --mode both --dry-run
```

## Real Run

```bash
OPENAI_API_KEY=... python3 -m prompt_policy_llm.eval_omnimath --limit 10 --mode both
```

Useful options:

- `--controller-model HuggingFaceTB/SmolLM2-135M-Instruct`
- `--controller-tokens 30`
- `--controller-samples 4`
- `--shuffle --seed 7`
- `--max-difficulty 4`
- `--dataset-path path/to/omni_math_rule.jsonl`
- `--output-dir runs/omni_math_rule`

## Outputs

Each run writes a timestamped directory:

- `predictions.jsonl`: one row per Luna call.
- `metrics.json`: accuracy, lift, latency, token counts, and estimated Luna cost.
- `controller_rollouts.jsonl`: reward-labeled actions for RL or GRPO-style training.
- `controller_sft_seed.jsonl`: chat-format best observed controller actions for supervised warm start.

## Training Format

`controller_rollouts.jsonl` is the main improvement artifact. Each row has:

- `messages`: controller system prompt and benchmark state.
- `action`: controller instruction.
- `reward`: verifier score.
- `baseline_reward`: zero-shot Luna score for the same problem.
- `advantage`: controlled score minus baseline score.
- `metadata`: benchmark and cost details.

The metadata keeps solver and controller budgets separate:

- `input_tokens` and `output_tokens`: Luna API token usage.
- `controller_output_tokens`: emitted controller action length.
- `controller_token_budget`: configured controller action budget.
- `controller_latency_s`: local controller inference latency.
- `backend_latency_s`: Luna solver latency.

That is enough to group samples by `group_id` and run a GRPO-style update over controller actions.

## Training Validation

Validate the SFT training path without updating weights:

```bash
python3 -m prompt_policy_llm.train_controller \
  --train-file runs/omni_math_rule/<run-id>/controller_sft_seed.jsonl \
  --validate-only
```

Check only the JSONL format, without loading the model:

```bash
python3 -m prompt_policy_llm.train_controller \
  --train-file runs/omni_math_rule/<run-id>/controller_sft_seed.jsonl \
  --dry-run
```

When ready to actually fine-tune:

```bash
python3 -m prompt_policy_llm.train_controller \
  --train-file runs/omni_math_rule/<run-id>/controller_sft_seed.jsonl \
  --output-dir models/smollm2_135m_controller_sft
```

## B200 Notes

For the B200, stage the repo under `/home/criteo/prompt_policy_llm`, then run:

```bash
bash scripts/b200_setup.sh
bash scripts/b200_validate_training.sh
```

Do not launch training until the validation pass succeeds. The eventual launch command is:

```bash
bash scripts/b200_launch_sft.sh
```
