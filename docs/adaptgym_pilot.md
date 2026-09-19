# AdaptGym paired session pilot

`src/prompt_policy_llm/adaptgym_pilot.py` evaluates frozen Luna with current-session
text against the same Luna configuration plus all notes from earlier sessions.
Qwen3-1.7B only manages notes; it never answers evaluation questions or trains.

Protocol: evaluate both arms, then show Qwen only the current session's public
text. Qwen reads notes through an executed `read_notes` call and emits strict JSON
`write_note`, `update_note`, and `no_op` calls. Exactly one call is accepted per response; duplicate JSON keys are rejected.
Arguments, dependencies, and the
120-word note budget are validated transactionally. Tool results are returned
for up to six rounds. This is a local JSON tool protocol, not native API tool calls.
Every session starts a fresh conversation. Each user starts with empty notes.

Ten seeds: 17,29,43,59,71,89,101,113,127,139. Ten sessions per user, five slots,
two distractors per session, update probability .35, four options per question.
All preferences revealed through the current session are queried; unseen hidden
preferences are excluded. Questions use prefix truth, never final-profile labels.
Answers/options/metadata/evaluator feedback are never given to Qwen. All notes
are given to the memory answerer without retrieval filtering. Identical inputs
(including session one) reuse a single Luna response to enforce exact parity.
Distinct arm call order is seeded. The API is stateless, with no previous-response
ID; temperature and seed are unset because endpoint support is not assumed.

Luna: `gpt-5.6-luna`, low reasoning, 1024 output tokens, no retries, no stored
responses. Qwen: pinned revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`,
BF16, greedy decoding, thinking disabled, 384 output tokens per tool round.
Maximum actual prompt lengths, runtime versions and model context limit are logged.
Failures remain in accuracy denominators. Delays refer to latest true profile
event; `current_text_mentions_answer` also identifies possible repetition/lures.
Cost estimates use existing repository rates and exclude GPU cost.

Local tests (AdaptGym is a separate source dependency):

```bash
PYTHONPATH=src:../../2026_Q3_AdaptGym/src python3 -m pytest -q
```

Set the AdaptGym path to its actual location. On RecoAtlas:

```bash
/home/criteo/qwen17b-work/prompt_policy_llm/scripts/b200_adaptgym_pilot.sh \
  --output /home/criteo/qwen17b-work/runs/UNIQUE_RUN_NAME
```

Artifacts: `answer_calls.jsonl` (exact prompts/outputs/usage), `scores.jsonl`
(paired answers and evaluator labels), `note_traces.jsonl` (all calls/results and
before/after stores), `evaluator_episodes.jsonl` (truth, kept outside model input),
`metrics.json`, `run_config.json`. A small real API and GPU/tool smoke precedes
any pilot. Credentials are parsed from an existing env file without logging values.

TODO: later add profile-based recommendation tasks and catalog/search evaluation,
including explicitly supplied age/gender/education when relevant to the user task.
Do not infer preference stereotypes from demographics. This pilot tests stated
preference recovery only, not recommendation quality or general personalization.
