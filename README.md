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

To give Luna native reasoning budget and include a concise derivation in the
saved trace, add `--think-mode` and `--show-work`:

```bash
python3 -m prompt_policy_llm.eval_omnimath \
  --limit 10 --mode both --think-mode low --show-work --max-output-tokens 1024
```

`--think-mode` accepts `none`, `minimal`, `low`, `medium`, `high`, or `xhigh`.
It controls Luna's native reasoning effort; `--show-work` controls whether the
visible response contains a concise derivation before its boxed answer.

## Teacher Hint Data

Generate verified controller supervision with a selectable teacher, including Luna
itself or a stronger configured model.
The pipeline runs (or reads) a baseline, asks the teacher for bounded short hints,
runs frozen Luna with every accepted hint, and retains structured examples where a
baseline miss flips to a correct hinted answer. It never starts training.

The command defaults to one problem and one candidate. By default it only calls
the teacher on baseline misses; use `--teacher-on-all` to override that behavior.

For a reproducible answer-aware Sol oracle upper bound, the harness first scores
a fresh Luna baseline on at most 20 items, selects exactly five current failures,
then gives Sol the original problem plus the trusted reference answer for private
checking. Luna receives only the original problem plus a parser-approved hint,
never the reference answer. If fewer than five failures are found, no hints are
generated and the recorded shortage is reported. This is not deployment-valid.

```bash
OPENAI_API_KEY=... python3 -m prompt_policy_llm.teacher_hints \
  --teacher-model gpt-5.6-sol --teacher-reasoning-effort low \
  --think-mode low --max-output-tokens 1024 \
  --answer-aware-teacher --candidates 1 --target-current-failures 5 \
  --max-baseline-search 20 --output-dir runs/sol_oracle_current_failure_5
```

```bash
OPENAI_API_KEY=... python3 -m prompt_policy_llm.teacher_hints \
  --limit 1 --candidates 1 --teacher-on-all \
  --max-output-tokens 512 --teacher-max-output-tokens 128
```

For a no-spend shape check, add `--dry-run`. To reuse a prior baseline run rather
than call Luna again, pass `--baseline-predictions path/to/predictions.jsonl`.

For oracle data generation, `--answer-aware-teacher` gives the teacher the trusted
verifier answer for private checking only. The answerer never receives it: it gets
only the original problem plus a leak-checked hint. This is an upper-bound data
generation experiment, not a deployment evaluation.

Each run writes `baselines.jsonl`, raw `teacher_proposals.jsonl`, verified
`verified_teacher_candidates.jsonl`, flip-only `teacher_flips_sft.jsonl`, and
`metrics.json` with teacher, solver, and total estimated cost.

### Local LFM2 Hint Provider

Use `LiquidAI/LFM2-350M-Math` locally as the deployment-valid controller-hint
provider while keeping Luna as the frozen answerer:

```bash
OPENAI_API_KEY=... python3 -m prompt_policy_llm.teacher_hints \
  --hint-model lfm2-350m-math --limit 1 --candidates 1 --teacher-on-all
```

The model is loaded lazily only when an eligible hint is requested. Install the
local runtime with `pip install -e '.[local-hints]'`; LFM2 requires
`transformers>=4.55`. The provider uses the model's single-turn chat template and
never receives a trusted reference answer or baseline answer text. It targets
8-16 tokens, uses a hard `max_new_tokens=30` cap, and then passes the existing
30-word/leak parser before Luna receives any hint. `--answer-aware-teacher` is
intentionally rejected with this provider. Use `--local-hint-device auto|cpu|cuda|mps`
to select a local device.

## Critic Oracle

`compare-critic-oracle` compares direct Luna thinking with an answer-aware
plan/critic/executor upper bound. The critic can see the trusted answer, but the
final frozen executor receives only the original problem plus leak-checked plan
and critique. This is explicitly not deployment-valid.

```bash
OPENAI_API_KEY=... python3 -m prompt_policy_llm.critic_oracle \
  --problem-ids HMMT_11:620,HMMT_2:1320,fermat:885,HMMT_11:510,HMMT_2:1199 \
  --min-difficulty 2.5 --max-difficulty 4
```

The run writes:

- `predictions.jsonl`: baseline and controlled responses.
- `metrics.json`: accuracy, lift, latency, token counts, and estimated Luna cost.
- `controller_rollouts.jsonl`: reward-labeled controller actions for RL or GRPO-style training.
- `controller_sft_seed.jsonl`: chat-format best-action rows for supervised warm starts.
- `traces.txt`: one readable trace per problem, with prompt-policy hint, solver output,
  extracted answer, reference answer, and score.

To isolate an answerer-budget change while preserving an oracle's exact accepted
hints, pass `--cached-hints-from path/to/teacher_proposals.jsonl` with the same
`--problem-ids`. This makes no teacher calls and writes SHA-256 source/replay hint
identity records to `cached_hint_provenance.json`.

## Repository Shape

- `docs/` contains research and experiment design notes.
- `configs/` contains benchmark and controller configuration sketches.
- `src/prompt_policy_llm/` contains the emerging Python package.
- `tests/` contains smoke tests for configuration and harness code.

## AdaptGym Session Memory Pilot

`eval-adaptgym-pilot` compares frozen Luna with current-session evidence against
identical Luna settings plus all prior-session notes maintained by fixed-weight
Qwen3-1.7B. Every session is scored before the note update. Qwen executes validated
read/write/update/no-op tools and never sees evaluator labels or future events.

The bounded pilot uses ten synthetic users and ten sessions, with prefix-only
preference questions, paired traces, action-validity metrics and temporal audits.
Install the `adaptgym` extra and place the separate AdaptGym `src` on `PYTHONPATH`.
See [the protocol and Coder launch instructions](docs/adaptgym_pilot.md).
No controller training is performed.
