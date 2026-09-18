# All100-session structured GRPO run

The user has authorized all100existing sessions/10users as training data. Earlier split labels in the data export are provenance only for this run; nothing here is held out. Historical dates/wording and gold/scoring semantics remain unchanged.

Execution order: bounded GPU optimizer smoke; frozen prompted Qwen3-4B baseline; one chronological pass through all100training contexts; matched trained-adapter evaluation. Baseline and post-training evaluation each sample four continuations per context with the same prompt, schema, budget, decoder and matched per-session seeds. Candidate0 alone determines carried memory; invalid candidate0 retains the incoming own prediction. Other candidates never affect carry-forward selection. No gold previous notes, future sessions, or Luna enter the policy.

Training also samples four isolated candidates from identical incoming memory. Every session is logged even if all candidates are invalid or rewards tie; such groups produce no optimizer update and are reported, never silently omitted. Notes reset between users. Checkpoints are saved every25groups to stay within the observed9.76GB free disk; model weights are not committed to Git.

Primary metric: mean over sessions of the mean of four `correct_current_fields / target_fields`. Report per-user/session counts, aggregate raw/micro counts, candidate0, mean, best and worst counts, valid JSON, missing/incorrect/unsupported fields, exact-state candidates, and exact-state pass@4. Pass@4 requires at least one candidate matching every revealed current field with no unsupported claims; history is diagnostic, not part of the reward or exact-current-state criterion.

The persistent goal is a reproducible in-sample improvement over the prompted base, not merely a checkpoint. A single matched seed is preliminary. Repeat matched-seed comparisons, keep prompt/scorer/data fixed within comparisons, record all attempts, and do not choose best traces or user subsets after observing scores. If tuning changes prompt or budgets, run a newly matched frozen baseline before attributing improvement to training. Raw correct-count reward remains unchanged.

The sampler batches four continuations on the existing B200 allocation. Training likelihood/backward runs in train mode (all adapter/attention dropout is zero) so activation checkpointing is effective; generation runs in eval mode. This corrects the earlier scaffold's eval-mode checkpointing issue. The unchanged loss applies group advantages only to assistant continuation tokens with clip0.2, KL0.02 and gradient clipping1.

Commands are recorded here, not auto-executed by this document. Use `structured_config.json` with one step for the separate smoke, then `structured_all100_config.json` with `--steps100` through `python -m prompt_policy_llm.train_note_grpo`. Actual CLI syntax is `--steps 100`. No cache or credentials argument is needed for extraction_count mode.

## Sparse-update revision

After smoke02 generated four malformed full documents, the policy interface was changed at user request to sparse JSON updates with profile and optional history. Omitted fields retain prior policy memory; present atomic fields replace the exact scope, including complete list/compound values. Null and empty lists preserve their original meaning. Runtime supplies version/as_of and scores the accumulated profile. Invalid updates still receive zero. Frozen baseline and trained evaluation share this interface. Gold targets and raw-count scoring remain unchanged. Smoke01 failed on optional torchao compatibility; runtime torchao alone was upgraded from 0.9 to 0.16 without dependencies. Smoke02 loaded the model and verified checkpoint reload but performed no optimizer update. Original remote smoke artifacts are retained.

### Native tool and plain-text input revision

Session input is now plain text: current time, then each unchanged statement text with its timestamp. Statement IDs and the JSON observation wrapper are not shown to the policy. Previous saved profile memory remains structured. The native Qwen tool schema exposes update_profile with sparse profile and optional history arguments. Exactly one well-formed tool call is required; no JSON repair or relaxed schema validation. Baseline, training and evaluation use the same rendering and tool interface.

### User-directed plain-text fact matching

The current policy emits sparse descriptive key: value lines; keys are optional for distinctive values. Both session input and previous saved notes are plain text. The evaluator keeps original private JSON targets, matches normalized whole values (complete lists/compound values), counts targets once, and uses descriptive key overlap to disambiguate repeated values. Unknown/empty/common short values need context. Matching normalizes case, punctuation, list order and a small explicit unit/key alias table; it is deterministic, not an LLM judge. It does not infer arbitrary paraphrases. Updates replace identical normalized keys; omitted notes persist, so synonymous key changes can leave duplicates or stale notes (reported limitation). Explicit historical lines are excluded from current credit. The reward is the raw count of matched current facts; no penalties or normalized reward. Invalid line format gets zero. This supersedes the JSON-output and native-tool revisions, whose failed artifacts remain.

### Final reward clarification: value intersection

The user clarified that reward is simply the intersection of extracted note values and target values; keys do not gate credit. Reward now counts unique normalized values in both sets, not distinct scoped fields sharing the same value. Both the unique-value denominator and original field count are recorded. Common values and historical/wrong-key mentions can therefore match; key/scope correctness is not claimed by this metric. No semantic judge, repair, or extra penalty is added. The first plain-text smoke used the earlier context-aware matcher and is preserved as an obsolete reward diagnostic; subsequent runs use value intersection.

### Cumulative session context

At the user’s correction, each session t now receives raw statements from sessions1..t in chronological order, plus its own saved notes. Future sessions and evaluator targets remain excluded. Current time is that of session t. Baseline, GRPO and trained evaluation share this renderer; previously completed smokes used current-session plus prior notes and are not cumulative-context results.
