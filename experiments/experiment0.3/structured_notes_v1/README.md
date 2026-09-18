# Direct extraction-count notes: data and reward ready for review

**100 post-session gold targets from 10 existing users. Zero external model calls, zero GPU runs, zero training steps.** The generator, session wording, dates and historical evaluation artifacts are unchanged.

Inspect [first, middle and final Maya profile targets](EXAMPLES.md), [deterministic scoring examples](scoring_examples.json), [manifest and splits](manifest.json), [target validation](validation.json), and [exact policy prompt](policy_system.txt).

## What the JSON represents

The `profile` value uses the **original profile field names and types**, progressively filled from the revealed prefix. It is a partial original profile, not a new flat fact list. Examples include `personal.name`, `professional.income`, `category_profiles[].preferences`, `scoped_overrides`, `sizes`, `general_preferences`, and `purchase_intents`.

Absent fields are unrevealed. An explicitly unknown value is `null`; an explicitly empty preference is `[]`. Structural identity fields such as category, brand/system, context, recipient and intent ID select a field; they do not earn separate points. No age inference or hidden default/profile fields are filled.

A note transport envelope adds `version`, `as_of`, and an **optional** `history` sidecar. History retains dated updates and temporary base values for future restoration. Its correctness is a separate diagnostic: omitted or factually inaccurate but schema-valid history does **not** reduce current-field reward. Schema-invalid JSON receives zero, including malformed optional history. See [envelope schema](schema.json) and [field/identity contract](address_guide.json); the mandatory Python runtime validator additionally enforces nested field types, exact compound shapes, identity uniqueness, scope and chronology.

## Exact reward contract

**Reward = number of correctly recovered current, revealed, scoped profile fields.** No clipping, normalization, F1, utility term, history requirement, length penalty or hallucination penalty is added.

One atomic extraction is:

- One scalar profile attribute, such as name or occupation.
- One complete typed preference/hobby/language collection. Lists are order-independent, but the entire collection must match; subsets, supersets and extra guesses do not earn the point.
- One complete compound attribute, such as income, residence, education, height/weight, default size or intent budget.
- One size at an exact category/brand/sizing-system address.
- One scoped stance. Retraction is an explicit current value.
- One intent `status` or `deadline`, scored separately at the correct ID/category/recipient scope.

Missing fields get no points. Wrong current values, stale values and wrong scopes get no points. Duplicate JSON keys, duplicate identities/addresses and duplicate collection members are invalid and receive zero for the document. Explicit unknown values earn credit only where that same field was explicitly revealed as unknown.

`correct / target_count`, missing, incorrect, unsupported, semantic exact-state accuracy, and history accuracy are diagnostics only. **Unsupported extra fields do not subtract correct points.** That is a limitation of the requested raw-count objective, recorded openly rather than adding an unapproved penalty. Identity collisions and multiple guesses at one field are rejected, so a list of every answer cannot collect that field's point.

For Maya session1 there are nine scored fields. The saved examples give: perfect=9; no history=9; one missing=8; one wrong=8; materials superset=8; duplicate category=0; invalid JSON=0. Adding a hidden unknown hair-color field remains9, with unsupported=1 and exact_state=false—it earns no additional point.

## Temporal semantics and gold provenance

Gold is recomputed from substantive events in the prefix, not copied from the full hidden profile. Full profile metadata is used privately only to map revealed scoped identities to original fields. Repetitions/filler do not create history. All100 prefix current values were checked against the archived private oracle.

Original semantics remain: temporary `until` timestamps are exclusive and restore the latest applicable prior value; intent deadlines are inclusive and active expires strictly afterwards unless completed/cancelled. Explicit updates/corrections/retractions replace current values while history may retain previous values. No date wording or timestamp interpretation changed.

## Split and leakage boundary

| Split | Users | Sessions | Interpretation |
|---|---|---:|---|
| Train | user06–user08 | 30 | Three existing users |
| Development | user01–user05 | 50 | Includes the three inspected users and pre-stop overshoot users |
| Validation | user09–user10 | 20 | Reserved existing-cohort validation, **not pristine confirmatory test** |

Whole users stay in one split. All profiles share synthetic templates/design and have been exported/validated; no fresh unseen-user generalization claim is appropriate.

`public/` contains only current time and user statements. `evaluator_only/` contains the100 gold note envelopes. Split JSONL files describe rollout examples and target locations; they are **not** teacher-forced SFT pairs. The manager receives only the current public observation and its own previously predicted JSON. It never receives previous gold notes, questions, hidden profile, target counts, future sessions or gold. Invalid predictions retain the last valid own memory for subsequent sessions; the invalid update receives zero.

## RL integration and remaining gate

The existing `train_note_grpo` entry point now dispatches `reward_mode: extraction_count` to `train_structured_grpo`. It requires no Luna/cache/credentials. The direct mode samples four JSON continuations from an identical own-prediction prefix; gold is loaded only after generation. Raw counts feed the existing group-normalized advantages, assistant-token-only loss, clip0.2 and reference-KL0.02. The reward itself is not standardized or penalized; GRPO's advantage normalization remains an optimizer operation.

[Configuration](../structured_config.json): frozen Qwen3-4B BF16, standard LoRA rank16/alpha32/dropout0, attention+MLP projections, LR1e-5, gradient checkpointing. The structured output cap is8192 tokens, within the existing16384 total-context guard; long prompts fail explicitly rather than truncate. The smoke schedule exercises sessions1,5,10 using exclusively policy-generated prefixes. Checkpoints, optimizer/RNG state, source hashes and reload checks are implemented.

**Readiness is CPU/data-path readiness only.** The direct JSON policy and GPU optimizer have not yet been run. A smallest GPU smoke, adapter-update/reload verification, and matched frozen-versus-adapter structured evaluation remain the next review gates. Free-form prompted baseline results are not a matched structured-policy baseline. No new job was launched by this work.

## Reproduction

From the repository root, use a new output directory:

```sh
PYTHONPATH=src python3 experiments/experiment0.3/export_structured_notes.py \
  --source experiments/experiment0.2/dataset_v1 --output /path/to/new-export
PYTHONPATH=src python3 -m pytest tests/test_structured_notes.py tests/test_note_rl.py tests/test_explicit_memory.py -q
```

The export is deterministic and does not call any model. The policy/scorer implementation is in `src/prompt_policy_llm/structured_notes.py`; internal revealed-record replay is in `structured_note_records.py`; policy-only state propagation is in `structured_note_rollouts.py`.
