# Design: train Qwen to retain useful explicit-state memory

Status: design only, written after experiment checkpoint commit `3267e04` on 2026-09-17. No training, new data generation or paid evaluation is launched by this plan. The recommendations below are proposed starting settings, not validated hyperparameters.

## Objective and evidence

Train a note policy starting from verified `Qwen/Qwen3-1.7B` revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Keep the pretrained base weights frozen when training adapters; the note policy changes through those adapter weights. Keep the answerer, environment, schema, scoring contract and evaluation splits frozen within a run.

The objective is accurate future explicit-state recall under a memory budget. Tool syntax is necessary but insufficient. The original Maya comparison was40% versus50% with identical empty-note inputs and therefore showed no memory benefit. Native tools fixed much of the invocation problem; the coverage-focused prompt still saved filler/unsupported attributes and missed session2 updates. Treat these as regression fixtures, not successful demonstrations.

Use the sequential explicit-state environment, not the archived recommendation/utility task. Keep notes as actual model-written natural language through read_notes, put_note, delete_note and no_op. Do not teach the model to emit hidden profiles, answer keys or precomputed oracle notes.

## What the repository has and what is missing

- `src/prompt_policy_llm/explicit_memory.py`: coherent-profile session generation, public observation boundary, revealed-state oracle, strict transactional note dispatcher, paired Luna answering, Qwen identity verification and saved traces.
- `explicit_note_tools.py`: native Qwen tools-aware chat template and strict wrapper parser. `explicit_note_coverage.py`: a two-session manager with a first-finish coverage review. Extract a reusable manager and freeze one exact protocol for training and evaluation; the original textual protocol and native protocol are different conditions.
- `profile_contract.py` and experiment0.1/profile_generation: profile/schema/fixed-constraint validation. These reject invalid environments; they are not a learned-note quality reward.
- `train_controller.py`: ordinary Transformers Trainer SFT, currently trains the loaded model directly. `training_data.py` renders custom `<|role|>` strings and a final assistant completion; it does not preserve native Qwen tool-call rendering or multi-turn assistant masks. Neither is ready unchanged for note SFT.
- `finetune.py`: creates reward-labeled short-instruction rows and baseline advantages. It is a data exporter, not an RL optimizer. No GRPO/PPO trainer is implemented in this repository. `pyproject.toml` does not currently specify TRL or PEFT.
- The existing B200 SFT shell scripts are reusable launch-pattern references, not a multi-turn RL pipeline. Their working-tree changes and `configs/training/qwen3_1_7b_sft.yaml` belong to other work and were intentionally excluded from the experiment commit. The latter's30-token instruction/1024-token context assumptions must not be inherited for note trajectories.

Proposed new modules: `note_environment.py` (public state and private scoring boundary), `note_rollouts.py` (native tool trajectories and assistant masks), `note_reward.py` (versioned reward components), `note_sft.py` (optional verified bootstrap), `train_note_grpo.py` (adapter training), `eval_note_policy.py` (paired sequential evaluation). Proposed config: `configs/training/note_grpo.yaml`; launcher: `scripts/b200_launch_note_grpo.sh`. These names are a work breakdown, not files already implemented.

## Environment and information boundary

At session t, the policy sees the current dated statements and can read notes from sessions before t. It never sees hidden profile fields, event metadata, question options, answers, rewards, future statements or evaluator coverage labels. Tools execute transactionally; malformed calls do not mutate state. Reset notes and all conversation/KV state between users. Only explicit notes cross sessions.

Keep the existing12-call,768-output-token-per-call,40-note and1600-word limits for the first matched experiment. Record serialized memory tokens as an additional metric; define a tokenizer-based limit before any later compression experiment. Account for the full rendered prompt against model context length. The coverage-review tool response, if retained, counts toward the same call budget and is identical for trained and frozen policies. Do not add oracle missing-fact hints after failed coverage.

Gold state remains private to the scorer and includes only the revealed prefix at the scoring time. Retractions, historical values and temporary overrides are facts with validity intervals, not contradictions merely because they differ from the current value. Historical expired intents remain valid historical notes; distinguish stored stale assertions of current status from accurately dated old status.

## Primary reward: incremental future recall

For a shared incoming state `(O_t, N_before)`, sample candidate note-update trajectories z, yielding `N_z`. Define a reference branch `N_ref = N_before`: the same state with the current update omitted. This measures the update's incremental utility, rather than crediting inherited good notes. Also report an empty-notes branch for end-to-end memory benefit.

Build evaluator-only probe sets `Q_t,h` at future delays h from disclosed prefix facts. Current future-session statements must not disclose, repeat, correct or otherwise determine the probed target. Require a dependency on evidence already seen by t; exclude targets changed by intervening events from the static-note diagnostic. Advance the clock to include temporary expiry and intent deadline probes. Include current-state and historical-time questions. Do not classify a question as memory-dependent merely because baseline got it wrong. Use causal provenance and counterfactual tests: vary the earlier fact while holding the future public observation fixed; its correct answer must change.

For the initial training objective, evaluate both candidate and reference notes at these matched future observations **without intervening note-policy updates**. This is a short-horizon counterfactual probe, not a claim of full online performance. Validate trained policies separately on real ten-session rollouts, where answers always precede the current session's note update.

Let A be exact recall correctness averaged over a balanced set of probe types, with invalid/missing answer outputs scored zero. Let each horizon receive normalized weight w_h (initially equal weights for next-session and one later-session/expiry probes).

```
U(z) = sum_h w_h * mean_q [ E A(Luna(O_future, N_z), q)
                         - E A(Luna(O_future, N_ref), q) ]
```

U lies in[-1,1]. It is the primary quality term. It rewards information preserved by this update, and penalizes destructive edits that reduce future recall relative to retaining the old notes. Include retention probes on old facts so replacing a note cannot gain on new facts while silently losing unrelated ones. Use the empty-notes contrast only as a secondary end-to-end metric; otherwise good inherited notes can obscure a bad current update.

Proposed total sequence reward:

```
If no valid read→write/review→finish trajectory within hard limits:
    R(z) = -1
Else:
    R(z) = clip(U(z) + 0.20*C(z) - 0.50*H(z) - 0.10*F(z)
                        - 0.05*B(z) - 0.05*I(z), -1, 1)
```

A valid no-change trajectory may omit writes when there is truly nothing useful to add; do not require a write merely to earn validity. The first line means protocol-valid actions in dependency order and successful finalization, not that every attempted round must be valid. Invalid attempts that recover still contribute I. Do not grant a positive reward just for valid tools.

- C: macro-averaged supported fact F1 (0–1) across new/changed and sampled retention assertion groups, with correct value, scope and temporal qualifiers. Use a fixed evaluator target inventory from the revealed prefix, not counts of model-written statements. Missing IDs/recipients/expiry qualifiers reduce credit. Exact strings alone are not a semantic coverage metric.
- H: unsupported or materially contradictory claims, normalized by the fixed relevant assertion count and capped at1; never divide only by generated claim count (which invites dilution). Explicit false inference of a size, recipient, scope or current state is penalized. Keep a separate count of severe errors for go/no-go gating.
- F: saved irrelevant filler/third-person/product assertions, normalized against the same fixed inventory and capped at1. Quoting raw transcripts is not a free route to coverage.
- B: serialized memory budget utilization in[0,1], using the declared budget measure; report actual tokens too. The small coefficient makes compression subordinate to useful recall.
- I: rejected-call fraction over the fixed12-round budget. Also log absolute rejected calls, wasted tokens and failed finalization.

Weights are initial recommendations. Report every component, U-only and absolute memory accuracy, not just R. Cap dense auxiliaries so excellent formatting or coverage cannot disguise consistently negative future recall. On filler-only sessions without eligible probes, use a separate retention/control objective; do not fabricate U=0 rows and count them as evidence of recall learning. Unknown/unrevealed probes test abstention, but known-fact probes dominate so constant “unknown” is not rewarded.

## Scorer design and noise control

Keep actual `gpt-5.6-luna` as the frozen answerer for the first comparable experiment, with a recorded model ID, prompt hash, low reasoning, output cap and API version. API aliases may drift: retain a canary set and stop comparisons on unexplained drift; use a pinned snapshot if available. The answerer never trains on policy rewards.

Cache results by the complete rendered answer prompt, actual model/settings and probe version. **Identical candidate/reference payloads must share the same cached answer draws, giving exactly zero measured U**, unlike the independent empty-note calls that produced the original spurious10-point gap. Share reference draws across all GRPO candidates for a state; randomize candidate call order. Distinct prompts cannot be assumed to have common random seeds through this API. Use one draw for bounded training pilots, then3 independent draws on dev audit subsets and finalists; report uncertainty and human-review borderline examples. A reference constant cancels in within-state group advantages, but remains valuable for reward interpretation and acceptance gates.

Multiple-choice exact scoring is available now, but the current generator has easy “unknown” distractors and only two questions/session. Training probes should balance answer positions, use same-type plausible decoys, and include open-value recall or counterfactual option variants on held-out evaluation. Do not modify the archived dataset to do this; version a new training dataset/probe generator.

Natural-language note support is not mechanically solved by the current schema validator. Implement a separate, frozen claim extractor/evaluator that maps note claims to value/scope/time and evidence, followed by deterministic comparison against private revealed state. Permit paraphrases; exact IDs are helpful but not sufficient to certify truth. Calibrate this scorer on hand-reviewed supported, missing, hallucinated, wrong-scope, stale and filler examples before using C/H/F. Keep scorer uncertainty and disagreements visible; never call its output ground truth without validation. If it cannot achieve high precision on hallucination penalties, start with U and manually audited diagnostic coverage rather than optimize a noisy auxiliary. Privileged state is allowed only inside rewards, never as writer input or auto-generated deployed notes.

## Learning algorithm and delayed credit

Recommend a small multi-turn GRPO adapter pilot once reward and trace parity pass. For each identical incoming observation+notes state, sample G=4 complete note-edit trajectories under the current policy. Each candidate has isolated mutable notes and tools. Score the whole update with R, compute within-state centered advantages with a standard-deviation floor, and monitor zero-variance groups. Do not silently drop failed trajectories: they retain the negative reward. If all candidates fail, no ranking signal exists; this is a reason to consider bootstrap, not to manufacture positive rewards.

Apply the sequence advantage to assistant-generated action tokens only. Tool results, schemas, user text, reward metadata and padding must have zero loss mask. Log behavior-policy token log-probabilities and policy version; use clipped importance ratios and an explicitly configured KL term to the frozen starting policy. Do not concatenate tool observations and accidentally train the model to generate oracle/tool text. A trajectory includes all accepted/rejected action attempts until termination. Prefix-expanded SFT rows and full RL trajectories have different sampling units; report both counts.

Short-horizon counterfactual U assigns delayed recall credit to the entire session update. It does not identify the causal value of each individual put_note. After this works, test full-episode return-to-go across updates with on-policy trajectories; propagate future recall rewards only backward to preceding note actions. Consider leave-one-edit-out counterfactual diagnostics offline, not expensive per-token reward computation. Do not add dense shaping repeatedly for the same fact on every repeated statement.

Incoming memories should come from a versioned mixture of current-policy rollout prefixes and frozen-policy prefixes, never only perfect oracle memories. Avoid storing future-session information in replay states. Refresh on-policy prefixes frequently; if using stale samples, log age/ratios and enforce an explicit off-policy bound. Start with fresh synchronous groups before asynchronous rollouts.

Alternatives: PPO with a value head may become useful for long episodes/credit assignment but adds complexity; rejection-sampled SFT or DPO on audited whole-update preferences may be cheaper if rewards are too noisy for GRPO. These are alternatives to evaluate, not infrastructure already available.

## Optional SFT bootstrap, not a foregone conclusion

Compare frozen native-tools baseline, direct GRPO, and a small supervised bootstrap followed by the same GRPO budget. Bootstrap addresses valid read/edit/finish and factual completeness without pretending the existing bad notes are demonstrations. Obtain teacher-generated trajectories from public observation+prior notes only, reject those failing support/coverage audits, and include corrections, temporal changes and filler-only sessions. Do not copy evaluator state into teacher notes. Preserve the teacher/model/cost provenance.

A proposed initial cap is200–500 audited session-update demonstrations, at most one epoch, then stop if held-out support does not improve. Train using Qwen's native tools-aware tokenizer template with correctly masked assistant turns. Do not reuse the current30-token short-hint serializer. Retain the same12-call interaction protocol for teacher, policy and evaluation. Whether bootstrap is worth its generation/audit cost remains a decision after the dry-run signal test.

## Splits and reward-hacking defenses

The ten current users are development/debugging data: Maya has been inspected repeatedly. They are not an untouched test set and are too small for a credible RL result. Freeze their artifacts as regression fixtures. For a future pilot, propose separately generated user-disjoint train/dev/test cohorts (e.g.200/40/40 users, ten sessions each), with a manifest binding initial-profile hashes, generation seeds, render families and probe versions before optimization. This is a budget proposal, not approval to generate them now.

Split before session generation. Hold out combinations of brand/category/size systems, values, language paraphrase templates, timing patterns, temporary overrides and intent lifecycles; do not split sessions from one user across train/test. Deduplicate near-identical profiles and prompts. Keep fixed constraints broad enough that all users do not share the same predictable anchor values/deadlines. The present seeded storyline is suitable for plumbing but cannot support unseen-template claims. Include separately authored test templates and adversarial distractors, then lock the test set until final selection.

Defenses: no access to question letters in writer prompts; shuffle option labels; counterfactual target values; normalize by fixed gold inventory; penalize full-transcript filler; bound note length and calls; evaluate forgotten unqueried facts and old-note retention; test “always unknown”, “always active”, duplicate facts, unsupported generic sizes, future answer instructions and direct prompt injection in notes. Treat notes as quoted untrusted data in the answerer. Reward supplying supported state, not telling Luna which answer to select. Hold out probe templates from optimization and evaluate with an alternate frozen answerer on a small audit subset to detect answerer-specific tricks.

## Compute stages and go/no-go gates

1. **CPU implementation checks, no model calls.** Replay golden state, transactionality, no-op review, prefix isolation, token loss masks, same-input U=0, temporal boundaries, negative rewards and split deduplication. Corrupt one field deliberately and ensure the audit fails. Confirm adapter parameters alone are trainable.
2. **Reward calibration, bounded inference only.** Use saved failed traces plus a small manually audited set; establish scorer precision before penalties enter training. Create at most8 states ×4 candidate trajectories ×2 future observation batches:64 candidate and16 shared-reference Luna calls at one draw (up to80 total; each batch may hold multiple probes). Set a hard token/API-call cap and log actual costs. This is a proposed future stage, not executed. Avoid extrapolated runtime promises.
3. **Optimizer plumbing smoke.** One B200 allocation,2–5 steps, G=4, small microbatch, gradient accumulation and adapter-only BF16. Check finite gradients, nonzero assistant-token masks, genuine weight updates, stable tool-state isolation and checkpoint reload. Stop if reward groups are almost always tied or scorers drift.
4. **Bounded learning pilot.** Initially25–50 optimizer steps with held-out dev checks every10 steps. Start with horizons1 and a later/expiry probe; measure actual peak memory, tokens/sec and reward-call latency before scaling. Promote only when valid finalization is at least95%, supported precision at least95%, relevant coverage at least90% on audited dev data, and severe hallucinations are below1% of assertions. These are proposed acceptance thresholds, not achieved results. Require positive mean U with a user-cluster bootstrap interval above zero and no material regression on current-session questions or temporal/scope slices. If too few independent users make the interval uninformative, collect evidence rather than call it a win.
5. **Locked test evaluation.** Ten-session sequential rollouts, same current observations/questions for both arms, only prior notes added, both scored before note updates. Compare frozen-native policy, selected adapter and no-memory reference; include budget-matched baselines. Invalid answers and failed note updates remain in denominators. Bootstrap over users, not20 correlated Maya questions. Report protocol failures, factual support, hallucination/filler rates, current/historical/expiry/scope slices, all-query and valid-only accuracy, paired wins/losses, raw counts, memory size, model/tool latency and API usage.

For adapters, propose rank16, alpha32, dropout0, explicit q/k/v/o and gate/up/down projection targets, BF16 source weights and a conservative initial LR around1e-6 for RL (tune only on dev). Per the existing B200 guidance, compare ordinary LoRA with `pissa_niter_16` under matched data/seed/settings before selecting initialization. PiSSA requires preserving its residual base and initial adapter or verified conversion for the original base; verify initialization logit equivalence and checkpoint reload. Do not assume4-bit compatibility or PiSSA superiority. KL strength, optimizer/batch settings, sequence cap and precise TRL version must be pinned after a minimal compatibility smoke, not copied from unrelated defaults.

Known usable runtime from the completed experiment: `/home/criteo/verl-venv/bin/python`, model `/home/criteo/qwen17b-work/model`, NVIDIA B200 MIG3g.90gb reported by torch. Recheck current allocation/imports/memory before any future launch; do not assume access to a full B200. Start with synchronous local Transformers generation; add vLLM only after identical parser/template/trajectory semantics are verified and memory permits. The B200 skill's standalone server pattern is guidance from another workload, not an implemented path here. Pin Torch/Transformers/TRL/PEFT versions in a new lock/environment without breaking the existing venv.

Use a fresh persistent `/home/criteo/...` checkout/run directory. Launch with a checked-in wrapper and unique log/PID/exit markers; verify PID, command and initial log. Checkpoint optimizer, RNG, policy/ref adapters, rollout version and metric state. `nohup` survives SSH loss but not a stopped Coder workspace; keep durable artifacts out of `/tmp`. No training or remote process is started by this plan.

## Minimum ablations and decisions

Run ablations sequentially only after a positive pilot: U-only versus calibrated auxiliaries; no coverage reminder versus the frozen reminder protocol; direct GRPO versus audited SFT→GRPO; equal versus tighter note budgets; next-session versus longer-delay probes; no-update reference versus empty-memory diagnostic; ordinary LoRA versus PiSSA with matched budgets. Do not launch a broad parameter sweep.

Recommendations: native strict tools; future causal recall as primary reward; no-update counterfactual for per-update credit; same-payload cache equality; frozen answerer; adapter training; user/template-disjoint evaluation; stop on unsupported-fact regressions.

Unresolved decisions before execution: affordable cohort/teacher/API budget; whether scorer calibration is sufficient for dense C/H/F; whether protocol/coverage requires SFT bootstrap; exact supported TRL rollout API/version and loss-mask implementation; note token cap; horizon mix and group size after measured throughput; acceptance-threshold sample size; pinned Luna snapshot availability. These do not block saving the design and require no action from the user today. The first implementation milestone is an offline reward/rollout harness, not a training launch.

## External implementation references

The current official [TRL GRPO documentation](https://huggingface.co/docs/trl/grpo_trainer) describes GRPO configuration and tool/rollout support; verify the installed version's multi-turn behavior rather than assuming drop-in compatibility. The [TRL OpenEnv integration](https://github.com/huggingface/trl/blob/main/docs/source/openenv.md) illustrates a separate harness path, which may be unnecessary for this small local environment. These are candidate integration references, not dependencies already installed.

The official [PEFT PiSSA example](https://github.com/huggingface/peft/blob/main/examples/pissa_finetuning/pissa_finetuning.py) and [conversion notes](https://github.com/huggingface/peft/blob/main/examples/pissa_finetuning/README.md) support the adapter-initialization/conversion checks. Consulted2026-09-17; pin revisions for implementation.
