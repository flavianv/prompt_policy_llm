# Answer-Aware Critic Oracle Experiment

`compare-critic-oracle` compares two Luna paths on identical benchmark items.

- Arm A: direct frozen Luna with native `--think-mode low`, then a final answer.
- Arm B: Luna drafts a no-answer plan; a second Luna critic receives the problem,
  trusted verifier answer, and plan, then emits a constrained 1-5 rating, failure
  category, and optional concise repair; frozen Luna executes from only the
  original problem plus the leak-checked plan, rating, and repair.

The critic's trusted answer makes Arm B an answer-aware oracle upper bound. It is
not a deployment-valid prompting evaluation. The executor never receives the
reference answer. Plan and critic outputs are blocked before executor invocation
when incomplete, over their word caps, or answer-revealing.

The command defaults to one item. Reproduce the five-item oracle comparison:

```bash
OPENAI_API_KEY=... python3 -m prompt_policy_llm.critic_oracle \
  --problem-ids HMMT_11:620,HMMT_2:1320,fermat:885,HMMT_11:510,HMMT_2:1199 \
  --min-difficulty 2.5 --max-difficulty 4
```

The trace file gives per-item direct answer/score/latency/cost and oracle plan,
critic update, leak checks, executor answer/score/latency/cost. `metrics.json`
contains paired wins and losses. No model training is invoked.
