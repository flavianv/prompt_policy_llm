# All100-session structured GRPO run

The user has authorized all100existing sessions/10users as training data. Earlier split labels in the data export are provenance only for this run; nothing here is held out. Historical dates/wording and gold/scoring semantics remain unchanged.

Execution order: bounded GPU optimizer smoke; frozen prompted Qwen3-4B baseline; one chronological pass through all100training contexts; matched trained-adapter evaluation. Baseline and post-training evaluation each sample four continuations per context with the same prompt, schema, budget, decoder and matched per-session seeds. Candidate0 alone determines carried memory; invalid candidate0 retains the incoming own prediction. Other candidates never affect carry-forward selection. No gold previous notes, future sessions, or Luna enter the policy.

Training also samples four isolated candidates from identical incoming memory. Every session is logged even if all candidates are invalid or rewards tie; such groups produce no optimizer update and are reported, never silently omitted. Notes reset between users. Checkpoints are saved every25groups to stay within the observed9.76GB free disk; model weights are not committed to Git.

Primary metric: mean over sessions of the mean of four `correct_current_fields / target_fields`. Report per-user/session counts, aggregate raw/micro counts, candidate0, mean, best and worst counts, valid JSON, missing/incorrect/unsupported fields, exact-state candidates, and exact-state pass@4. Pass@4 requires at least one candidate matching every revealed current field with no unsupported claims; history is diagnostic, not part of the reward or exact-current-state criterion.

The persistent goal is a reproducible in-sample improvement over the prompted base, not merely a checkpoint. A single matched seed is preliminary. Repeat matched-seed comparisons, keep prompt/scorer/data fixed within comparisons, record all attempts, and do not choose best traces or user subsets after observing scores. If tuning changes prompt or budgets, run a newly matched frozen baseline before attributing improvement to training. Raw correct-count reward remains unchanged.

The sampler batches four continuations on the existing B200 allocation. Training likelihood/backward runs in train mode (all adapter/attention dropout is zero) so activation checkpointing is effective; generation runs in eval mode. This corrects the earlier scaffold's eval-mode checkpointing issue. The unchanged loss applies group advantages only to assistant continuation tokens with clip0.2, KL0.02 and gradient clipping1.

Commands are recorded here, not auto-executed by this document. Use `structured_config.json` with one step for the separate smoke, then `structured_all100_config.json` with `--steps100` through `python -m prompt_policy_llm.train_note_grpo`. Actual CLI syntax is `--steps 100`. No cache or credentials argument is needed for extraction_count mode.
