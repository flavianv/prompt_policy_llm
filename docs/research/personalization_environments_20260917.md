# Persistent shopping memory: two implementation reviews

Inspected 2026-09-17. Read-only source/data inspection; no downloaded code executed, dependencies installed, model inference, training, or new experiment. Recommendations below are discussion only.

**Recommendation:** use VitaBench 2.0's persistent-memory interface and executable catalog/tool architecture as design references. Use PUMA's parameter-training pipeline as a separate comparison. Neither release is a ready-made procedural RL environment for training Qwen to maintain notes while Luna remains frozen. Build that distinction into any proposal before implementing it.

## Evidence and versions

| Source | Paper age and revision | Inspected implementation/data |
|---|---|---|
| [VitaBench 2.0 paper](https://arxiv.org/abs/2605.27141) | v1 May 26, 2026; about 3.8 months old | [Code f60169e](https://github.com/meituan-longcat/VitaBench-2.0/tree/f60169e89f30499cb7883f3dad76bd03facc908d), latest commit July 14, 2026. [HF data a4553e1](https://huggingface.co/datasets/meituan-longcat/VitaBench-2.0/tree/a4553e13ec081be65cc37b48845da5819692d438), last modified June 4, 2026. |
| [PersonalWAB/PUMA paper](https://arxiv.org/abs/2410.17236) | first posted October 22, 2024; about 23 months old. v2 March 24, 2025; WWW 2025 | [Code and data 23ff65c](https://github.com/HongruCai/PersonalWAB/tree/23ff65c4c2288198b4b3d00d835760da2c2ff8e8), latest commit November 11, 2025. |

Paper dates are distinct from repository update dates. The [Vita website](https://vitabench2.github.io/) advertises 819 subtasks; the pinned JSON actually contains **56 users and 771 subtasks** (404 delivery, 223 instore, 144 OTA), matching the repository README. Cause of the discrepancy is unverified. JSON SHA256: `3a05f7e2742f204ae28b71db95b14e2daa94c9ff354f510a7d9c707564c7466e`.

PUMA's checked-in instructions contain **6,896 train / 2,174 test** tasks. Train: search 2,340, recommendation 2,221, review 2,335; test: 694 / 757 / 723 respectively. There are 1,000 profiles; 939 training users and 1,000 test users, with **939 overlapping**. Unique target ASINs: 6,708 train and 1,893 test, with 365 overlapping. This is neither a disjoint-user nor a wholly disjoint-target evaluation. These are direct JSON counts, not paper estimates.

## What “memory” and “training” actually mean

| Mechanism | VitaBench 2.0 | PersonalWAB / PUMA |
|---|---|---|
| Persistent explicit notes | `RewriteMemory` rewrites one text summary as new dated interactions arrive; retained when agent conversation resets. | PUMA's task-specific memory is retrieved history, not an evolving note store. |
| Who writes memory? | The agent's configured LLM is passed into `memory.update`; default updater and task solver share a model configuration. A separate Qwen updater needs an adapter. | Embedding retrieval and task-specific formatting select old purchases/reviews. No PUMA note-writing model is trained. |
| Other memory arms | Full raw context; embedding RAG over interaction chunks; null; hidden-ground-truth oracle. These are distinct from explicit notes. | Raw historical product/review features retrieved with MiniLM, then projected differently for search, recommendation, review. |
| Weight updates | No released RL/SFT memory-training pipeline found in inspected repository. Prompted rewriting is inference, not weight training. | Actual LoRA SFT for function selection and/or parameter generation; actual DPO for preferred tool parameters. Separate SASRec recommendation model/checkpoint. |
| Target of learning | Benchmark evaluates agents/memory strategies. | Web-function behavior and arguments, not retention, deletion, expiration, or note-edit policy. |

Vita's [memory interface][vbase], [rewrite implementation][vrewrite], [agent][vagent], and [orchestrator][vorch] establish this flow. Before each task, the orchestrator feeds that task's supplied historical interaction batch to the updater; it does **not** automatically turn every actual agent rollout into the next memory-update batch. It clears conversation state while retaining the memory object. Persistence across these sessions is real; durable restart/checkpoint semantics need separate integration. `RAGMemory` instead embeds and retrieves raw interaction chunks. `RewriteMemory` has an approximate 2,048-token instruction, and an append fallback on failed updates; that is not an enforced memory budget.

PUMA's [agent][pagent] filters history to review timestamp strictly before task timestamp, retrieves semantically similar entries, and formats product features, ASINs, or reviews. Its router directly reads ground-truth task `type` to select the memory representation. Treat that as privileged routing in comparisons, even though predicted function selection is also used downstream. The [SFT][psft] and [DPO][pdpo] scripts genuinely update model weights: LLaMA-2-7B, LoRA adapters plus specified embedding/head/layernorm modules. This is not implicit storage of a continually evolving individual user's profile through online training.

## VitaBench: executable environment, hidden preferences, and important caveats

The paper describes sequential personalized tasks, fragmented evidence, preference drift, and tool execution across three service domains. The implementation has mutable environment state, domain tools, simulated user interaction, and reward evaluation: useful environment components, but not an RL optimizer or an unlimited episode generator.

**Not all profile information must be extracted.** The agent [system prompt][vagent] directly injects all `user_profile` fields, including occupation, sex, birth date, addresses and health facts. Preference memory is a different field. Hidden preference snapshots and change records live in `user_scenario.personalized_preference_memory`; only the explicit oracle memory arm should receive those. A raw-history-only experiment must explicitly specify which account fields remain visible.

**Concrete flow from released data:** user `A891207` has dated histories describing hotel experiences. March 20 feedback favors trying Sheraton; March 26 evidence says Sheraton is preferred and wake-up calls are required because early meetings are common. On March 28 the user asks for two nights in Changchun next weekend, departing Friday. Memory is updated from those interactions, read into a fresh task context, and the agent searches/books from the current hotel catalog. The rubric asks for Sheraton, a double bed, wake-up service, and April 3–4 nights. Hidden truth records the broader Marriott preference changing to Sheraton and adds wake-up service. This supports preference updating and date resolution; it does not establish an explicit intent-status machine.

**Scoring:** [trajectory evaluator][vjudge] uses LLM rubric judgments, with all-expectations success and fractional rubric breakdowns. [Outcome evaluator][voutcome] examines action entities but still uses an LLM judge. The orchestrator defaults to trajectory evaluation and `enable_outcome_reward=False`; enabling the combined path uses the minimum of trajectory and outcome scores. Do not describe this as an entirely deterministic final-state oracle.

**Label assumptions require editing:** the first delivery case derives dietary scoring constraints from a PCOS profile field, rather than merely checking an explicitly stated food requirement. Those are benchmark assumptions, not medical guidance, and should not be transplanted. Likewise, do not infer taste from demographics. Ground-truth catalog metadata includes target/distraction labels and reasons; never expose raw task JSON to the policy. Delivery models use explicit public fields, but every adapted observation route still needs a leakage audit.

## PUMA: executable shopping and real training, but not memory-policy RL

The paper proposes task-specific retrieval, supervised function/parameter training, and DPO on scored candidate parameters. Its appendix reports LLaMA-2-7B, four 24GB A5000 GPUs, SFT and DPO. It is a useful concrete training precedent, but addresses another control surface.

**Concrete released example:** a timestamped search task asks for approximately $20 replacement parts for a robotic vacuum. The recorded target is an Electropan ILIFE filter/brush kit, ASIN `B08GC2KTG6`, priced $18. Prior purchases/reviews are filtered before the task time and retrieved. The model emits a search query; a static Lucene/BM25 catalog search returns products; scoring rewards choosing the search function and the recorded target's rank. This is not a free assessment that every compatible, under-budget alternative is good.

The [environment][penv] resets from a deep copy for each task. Search/recommendation/review calls terminate the task. Rewards are function accuracy plus target rank (`1 - index / result_count`) for search/recommendation, or embedding cosine similarity to the recorded review for review generation. A SASRec tool converts a history sequence into recommendations. The environment's returned task info contains targets: keep this out of policy input.

[Parameter supervision][pparam] uses generated search pseudo-labels, same-category historical ASINs for recommendation (falling back to the target ASIN when empty), and target reviews for review generation. [DPO preparation][pprep] selects highest/lowest scored candidate parameters, without an evident tie exclusion in that function. These are target-aware labels, not proof of rollout input leakage; preserve that distinction. The agent also deduplicates recommendation IDs through `set`, losing their order despite the sequential recommender interface.

## Temporal applicability and procedural-generation gap

| Requirement | VitaBench | PUMA |
|---|---|---|
| Evidence timestamps / current time | Dated interaction batches, subtask `current_time`, environment time; agent time updated for tasks. | Millisecond task and review timestamps used to exclude future history. |
| Elapsed-time reasoning | Possible from dates; not a standardized elapsed-time observation or expiry mechanism. | Retrieval cutoff and recency ordering; time gaps are not a dedicated reasoning/expiry objective. |
| Completion and deadlines | Booking/order dialogue, future dates and behavior events exist as evidence. | Historical purchase/review events; task termination exists, but no persistent active-intent lifecycle. |
| Explicit vs inferred expiration | No structured completed/cancelled/deadline-bound/open/uncertain state machine found. | No such lifecycle found. |
| Ground truth | Per-task preference snapshots/change records, rubrics, target entities. Not full truth for every latent intent/evidence provenance. | Target product/review and task type; profiles and history. No evolving note/intent oracle. |
| Procedural RL episodes | Fixed released evaluation JSON. No released general episode generator found. | Fixed train/test data and training-data preparation; not unlimited evolving-person generation. |

Direct Vita chronology audit: all 771 subtasks have nonempty `current_time`, but **3 environment times are blank**. Among 709 adjacent pairs with parseable environment times, **3 gaps are nonpositive**, and gaps range from about -353 to +467 days. This flags fields requiring reconciliation; it does not prove every intended session order is wrong. Do not silently sort tasks without checking preference-change chronology. Timestamped history alone does not guarantee temporally correct data or behavior.

For the requested procedural environment, generate a hidden evolving state and separately render observable evidence over sessions. Maintain stable/conditional profile facts separately from multiple active purchase intents. Brand/model-specific size and fit should retain their scope; a temporary budget or recipient-specific choice must not overwrite a permanent preference. Each fact/intent needs source evidence, observed time, valid time or deadline where known, status, and uncertainty. Keep hidden state, preference snapshots, target labels and reward explanations inaccessible to both Qwen and Luna.

**No universal ten-day TTL.** A lunch request ten days ago is generally no longer actionable; a trip planned months ahead may still be active. Explicit completion/cancellation closes an intent; elapsed deadlines can deactivate it; ambiguous open plans may need clarification. Inactive historical information can remain useful and need not be deleted. Distinguish a booking action completed today from the booked trip still in the future.

Test matched histories with only the current date changed, explicit cancellation versus silence, rescheduling, completed purchases, recurring needs, temporary exceptions and their end dates, simultaneous conflicting intents, and old stable preferences that remain valid. Include cases where the correct action is to ask rather than invent an expiry date. Do not make demographic traits or health diagnoses generative shortcuts to preferences or medical restrictions.

## Reuse proposal for Qwen note manager + frozen Luna

1. Reuse Vita's `update`/`read` separation and fresh task context, but route writes exclusively to Qwen and solve tasks exclusively with frozen Luna. Persist notes explicitly across session boundaries and reload them between processes if restart persistence is claimed. Log evidence cutoffs and per-session note diffs.
2. Borrow catalog/tool execution ideas; use unseen catalog items and shuffled IDs so success requires applying remembered constraints. PUMA's exact historical-ASIN reward is unsuitable as the sole recommendation reward. Separate user, event/template, and catalog splits; neither current release provides all of these safeguards.
3. Generate controllable hidden profiles, concurrent intents, timestamped evidence and state transitions. Hold out combinations and generator seeds/templates. Verify generated evidence actually supports the hidden truth; missing evidence must not be scored as a memory failure.
4. Score memory correctness separately: supported retention, scoped updates, contradiction resolution, active/inactive status, temporal applicability and evidence provenance, with penalties for unsupported inferences. Score downstream Luna choices for current intent constraints and catalog validity. Report each component before combining rewards; avoid rewarding empty notes or excessive deletion merely for lower stale-content counts.
5. Compare no memory, raw-history retrieval, prompted explicit notes, and eventually trained explicit-note policy under matched model, catalog, evidence, context/token budgets and frozen answerer. Train only the note manager if that is the scientific claim. RL algorithm selection and implementation remain future decisions.

## Reuse and runtime limits

Vita code is [MIT][vlicense], Python >=3.10, with external model/API configuration and dependencies including OpenAI client and tokenization/data tooling. The inspected HF snapshot has only `.gitattributes` and `tasks.json`, no dataset card/license metadata; do not assume the code license resolves external data rights. Chinese data is released; the README still calls the English benchmark forthcoming. No canonical train/validation/test split was present in the inspected tasks JSON.

PUMA is [CC BY-NC 4.0][plicense] with upstream attribution considerations. README specifies Python 3.11 / PyTorch 2.4.1 / CUDA 12.5 and Java; requirements are largely unpinned. Importing modules can download MiniLM models or load a SASRec checkpoint. Training scripts invoke DeepSpeed and use four GPUs, placeholder model/output paths and staged data preparation/adapter merging. The released SFT shell uses LR `3e-4`, while the paper appendix says `4e-3`; reproduce an explicitly chosen configuration, not an assumed match. The parameter script also contains a backslash followed by a space at its final continuation. Dependencies, script compatibility, API costs and runtime behavior were not execution-tested. Neither repository is certified turnkey by this review.

[vbase]: https://github.com/meituan-longcat/VitaBench-2.0/blob/f60169e89f30499cb7883f3dad76bd03facc908d/src/vita/memory/base.py
[vrewrite]: https://github.com/meituan-longcat/VitaBench-2.0/blob/f60169e89f30499cb7883f3dad76bd03facc908d/src/vita/memory/rewrite_memory.py
[vagent]: https://github.com/meituan-longcat/VitaBench-2.0/blob/f60169e89f30499cb7883f3dad76bd03facc908d/src/vita/agent/personalization_agent.py
[vorch]: https://github.com/meituan-longcat/VitaBench-2.0/blob/f60169e89f30499cb7883f3dad76bd03facc908d/src/vita/orchestrator/personalization_orchestrator.py
[vjudge]: https://github.com/meituan-longcat/VitaBench-2.0/blob/f60169e89f30499cb7883f3dad76bd03facc908d/src/vita/evaluator/evaluator_traj.py
[voutcome]: https://github.com/meituan-longcat/VitaBench-2.0/blob/f60169e89f30499cb7883f3dad76bd03facc908d/src/vita/evaluator/outcome_evaluator.py
[vlicense]: https://github.com/meituan-longcat/VitaBench-2.0/blob/f60169e89f30499cb7883f3dad76bd03facc908d/LICENSE
[pagent]: https://github.com/HongruCai/PersonalWAB/blob/23ff65c4c2288198b4b3d00d835760da2c2ff8e8/PersonalWAB/agents/puma_agent.py
[penv]: https://github.com/HongruCai/PersonalWAB/blob/23ff65c4c2288198b4b3d00d835760da2c2ff8e8/PersonalWAB/envs/base.py
[psft]: https://github.com/HongruCai/PersonalWAB/blob/23ff65c4c2288198b4b3d00d835760da2c2ff8e8/PUMA/finetune_llama.py
[pdpo]: https://github.com/HongruCai/PersonalWAB/blob/23ff65c4c2288198b4b3d00d835760da2c2ff8e8/PUMA/dpo_llama.py
[pparam]: https://github.com/HongruCai/PersonalWAB/blob/23ff65c4c2288198b4b3d00d835760da2c2ff8e8/PUMA/prepare_param_data.py
[pprep]: https://github.com/HongruCai/PersonalWAB/blob/23ff65c4c2288198b4b3d00d835760da2c2ff8e8/PUMA/prepare_dpo_data.py
[plicense]: https://github.com/HongruCai/PersonalWAB/blob/23ff65c4c2288198b4b3d00d835760da2c2ff8e8/LICENSE
