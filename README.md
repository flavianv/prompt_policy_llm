# Prompt Policy LLM

Prompt Policy LLM treats prompting as a control problem.

The project learns a tiny controller model that emits short instructions for a frozen frontier model. The controller sees task state, generates a compact prompt policy action of up to about 30 tokens, and is updated with reinforcement learning. The frontier model is never trained.

The thesis is simple: instead of searching for one static prompt, learn a policy for talking to intelligence.

## MVP

The MVP uses GPT-5.6 Luna as the frozen back-end model and starts with the smallest instruction-tuned controller worth probing:

- 135M parameters: `HuggingFaceTB/SmolLM2-135M-Instruct`
- 270M parameters
- 600M parameters
- 1.7B parameters

The controller receives benchmark state, emits a short steering instruction, and the frozen back end produces the final answer. Training starts with verifiable tasks where rewards can be computed automatically.

## Benchmarks

Initial evaluation targets:

- LiveCodeBench
- Omni-MATH rule
- ARC-AGI

The long-term arc is to prove the method on verifiable tasks, then move to noisier domains such as shopping and conversational recommendation.

## Primary Measures

- Lift over baseline prompting
- End-to-end latency
- End-to-end cost

## Core Loop

1. Build a baseline prompt for each benchmark.
2. Run the frozen back end with no learned controller.
3. Run each controller size with the same frozen back end.
4. Score answers with benchmark-specific verifiers.
5. Train the controller with RL, starting with a GRPO-style objective.
6. Report lift, latency, cost, and controller behavior.

## First Eval

Run a no-spend smoke test:

```bash
python3 -m prompt_policy_llm.eval_omnimath --limit 2 --mode both --dry-run
```

Run the real Luna baseline plus SmolLM2-135M controller:

```bash
OPENAI_API_KEY=... python3 -m prompt_policy_llm.eval_omnimath --limit 10 --mode both
```

Compare One Problem

For a direct, side-by-side inspection of a single problem, supply the problem and
its reference answer. The command runs Luna once without a controller and once
with the tiny controller's <=30-token instruction, then prints both raw outputs,
extracted answers, reference answers, exact-match scores, latency, and Luna cost.

```bash
OPENAI_API_KEY=... compare-policy \
  --problem 'What is 17 + 25?' \
  --answer '42' \
  --max-output-tokens 256
```

Use `--dry-run` to check the display without calling Luna or loading the local
controller model.

The run writes:

- `predictions.jsonl`: baseline and controlled responses.
- `metrics.json`: accuracy, lift, latency, token counts, and estimated Luna cost.
- `controller_rollouts.jsonl`: reward-labeled controller actions for RL or GRPO-style training.
- `controller_sft_seed.jsonl`: chat-format best-action rows for supervised warm starts.
- `traces.txt`: one readable trace per problem, with prompt-policy hint, solver output,
  extracted answer, reference answer, and score.

## Repository Shape

- `docs/` contains research and experiment design notes.
- `configs/` contains benchmark and controller configuration sketches.
- `src/prompt_policy_llm/` contains the emerging Python package.
- `tests/` contains smoke tests for configuration and harness code.
