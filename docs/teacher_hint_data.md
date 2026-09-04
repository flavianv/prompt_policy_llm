# Teacher-Generated Hint Data

`generate-teacher-hints` creates verified supervision for the small controller;
it does not train any model.

For every selected Omni-MATH rule problem, the pipeline first obtains a frozen
Luna baseline, unless `--baseline-predictions` supplies one. It normally calls
the teacher only when the baseline is wrong. In deployment-valid mode, the teacher
sees only the original problem: it receives neither Luna output nor the benchmark
reference answer. It proposes
up to `--candidates` diverse, one-line hints. The parser rejects hints that exceed
the 30-token whitespace budget or contain direct answer language / the reference
answer. The teacher is asked to target 8 to 16 tokens, while 30 tokens remains a
hard ceiling. An incomplete teacher response is rejected too. Every accepted hint
is then evaluated by the same frozen Luna backend and exact-match verifier as the
baseline.

The teacher is `gpt-5.6-terra` by default, while the frozen solver remains
`gpt-5.6-luna`. Luna is also a valid initial teacher: pass
`--teacher-model gpt-5.6-luna`. Change either model explicitly with
`--teacher-model` or `--luna-model`.

`--answer-aware-teacher` gives the teacher the verified answer only for private
reasoning/checking. The frozen answerer does not receive it; it sees only the
original problem plus a leak-checked hint. Mark these runs as oracle/upper-bound
data generation, never as deployment evaluations.
The default `--limit 1 --candidates 1` is intentionally spend-bounded.

Artifacts:

- `baselines.jsonl`: baseline solver output and score.
- `teacher_proposals.jsonl`: full teacher output, accepted hints, rejected hints,
  latency, token counts, and cost.
- `verified_teacher_candidates.jsonl`: state, hint, baseline result, hinted result,
  a leak check, and whether the verifier accepted it for training.
- `teacher_flips_sft.jsonl`: chat-format controller examples only for verified
  baseline-wrong to hinted-correct flips.
- `metrics.json`: proposal/candidate/flip counts and itemized estimated costs.

Use `--dry-run` for no external calls. `--teacher-on-all` asks the teacher even
for baseline-correct examples; avoid it for broad runs unless deliberately
collecting negative or redundant examples.

## Fresh Current-Failure Comparisons

Use `--target-current-failures 5 --max-baseline-search 20` to establish a fresh
Luna baseline under the exact answerer settings in the same command, select the
first five verifier-confirmed failures, and replay one or more teacher hints only
for that paired set. The search is capped at 20 items. A shortage is recorded and
no hint calls are made rather than falling back to stale failures or a different
configuration. `metrics.json` records paired hint-only wins, baseline-only wins,
both-correct, and both-wrong counts. For a stronger API teacher, set
`--teacher-model gpt-5.6-sol`; it remains answer-blind unless
`--answer-aware-teacher` explicitly declares an oracle run.

The Sol experiment command in the README uses `--answer-aware-teacher`: Sol gets
the trusted reference answer only for private checking and must return an
8-16-token, <=30-token non-answer repair hint. The parser rejects answer language
and any reference-answer string before Luna is replayed. Luna sees only the
problem and accepted hint. Label these artifacts `answer-aware oracle upper bound;
not deployment-valid`.

## Local LFM2 Deployment-Valid Hints

`--hint-model lfm2-350m-math` selects the official
`LiquidAI/LFM2-350M-Math` model as a local hint generator. It is a hint provider,
not the frozen answerer: the answerer remains Luna. The provider lazy-loads only
when it needs to emit an eligible hint, uses the model's one-turn chat template,
targets 8-16 tokens, and enforces `max_new_tokens=30` before the existing parser
enforces the separate 30-word and answer-leak gates.

Install with `pip install -e '.[local-hints]'`, which requires `torch` and
`transformers>=4.55`. `auto` selects CUDA, then Apple MPS, then CPU; override it
with `--local-hint-device`. In deployment-valid mode, no trusted verifier answer
or baseline answer is sent to the local model. `--answer-aware-teacher` is
rejected for this provider by design. Its artifact model name includes the actual
runtime device (for example, `LiquidAI/LFM2-350M-Math@mps`).
