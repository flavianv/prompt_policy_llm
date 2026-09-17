# Maya explicit-state smoke: protocol failure

Luna current-session-only scored **8/20 (40%)**; the designated memory arm scored **10/20 (50%)**, a +10 percentage-point difference. **Qwen produced no valid notes. All ten paired payloads were identical. The difference reflects separate Luna generations, not a demonstrated memory benefit.**

Paired outcomes: 2 memory-only correct, 0 baseline-only correct, 8 both correct, 10 both wrong. All 20 answer calls parsed successfully (40 individual arm answers). Failures remain in the denominator; all-query and valid-only accuracy coincide.

## Breakdown
| Evidence/query group | Questions | Current-session Luna | Designated memory arm |
|---|---:|---:|---:|
| Earlier-session evidence | 15 | 3/15 | 5/15 |
| Current-session evidence | 5 | 5/5 | 5/5 |
| Historical time | 3 | 0/3 | 0/3 |
| Current time | 17 | 8/17 | 10/17 |

Historical/current-time and evidence-source partitions overlap; do not add all four rows. Earlier-session evidence is based on the generator’s provenance flag, not proof that a baseline cannot guess.

## Per session
| Session | Current-session Luna | Designated memory arm |
|---|---:|---:|
| 1 | 2/2 | 2/2 |
| 2 | 1/2 | 2/2 |
| 3 | 1/2 | 1/2 |
| 4 | 1/2 | 1/2 |
| 5 | 1/2 | 1/2 |
| 6 | 0/2 | 0/2 |
| 7 | 0/2 | 0/2 |
| 8 | 1/2 | 1/2 |
| 9 | 1/2 | 1/2 |
| 10 | 0/2 | 1/2 |

## Protocol and models

Profile and answers: actual API model `gpt-5.6-luna`, low reasoning, independent calls, 768-token answer cap; API sampling defaults, no paired seed. Qwen notes: frozen `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, 12 files checksum-verified; bfloat16, greedy generation, thinking disabled, 768-token round cap, 12 rounds/session, NVIDIA B200 MIG 3g.90gb. No fine-tuning or optimizer.

Both arms receive identical current statements and questions; only the memory arm is eligible for prior notes. Both answers are generated and scored before the current note update. An offline audit replayed all answer payloads, explicit-state truth, score computation, note transitions, and the executed source checksum. Qwen receives only timestamped statement IDs/text, not questions, answer keys or the hidden profile. The session generator/evaluator uses hidden ground truth; model input does not.

## Note-tool failure analysis

Invocation: 120/120 rounds rejected; 0/10 sessions terminated successfully; 0 output-cap hits. This harness uses textual JSON tool calls with an application-side dispatcher, not native function calling. Qwen emitted multiple objects/prose, invented names such as `note` and `note_upsert`, or failed the mandatory `read_notes` dependency. Invalid calls leave notes unchanged.

Intent alignment: attempted outputs sometimes copied café/elevator chatter and other-person statements as user notes. None executed, so this is an observed attempted behavior, not stored contamination. Context awareness: no successful read/edit chain exists to demonstrate dependency compliance. Robustness: repeated generic error feedback did not recover within 12 rounds. No injected unavailable-tool test was run. Traceability: every prompt, response, tool result and before/after note snapshot is saved; this run has no exposed reasoning trace.

## Representative answer errors

Session 3: both missed restored summer-pants materials (linen/cotton after the temporary override expired). Session 6: both missed the completed gift intent. Session 7: both guessed the wrong name and historical income. All three historical questions failed in both arms. The two memory-arm-only successes were gift intent expiry in session 2 and reopened active status in session 10; their input payloads were identical to baseline, so they cannot support a memory claim.

## Scope and reproducibility

One synthetic LLM-generated user, ten sessions, twenty questions. This is a smoke test, not a statistically persuasive quality comparison. Multiple-choice guesses can be correct without evidence. Recommendation metrics (sethit, result cardinality, candidate coverage) do not apply to explicit-state recall. The next useful checkpoint is a separately labeled note-interface repair and validation, not reporting this +10-point difference as memory performance. No replacement live run was launched.

Raw artifacts: `answer_calls.jsonl`, `scores.jsonl`, `note_traces.jsonl`, `episode.json`, `run_config.json`, `metrics.json`, and `audit.json`. Exact executed source snapshot: `../src/prompt_policy_llm/explicit_memory.py`.

Measured Qwen generation time: 154.33 seconds; 200806 input and 16717 output tokens across 120 rounds. Luna answer calls: 66.96 seconds summed API latency, 14,614 input and 3,446 output tokens. These sums are generation latency, not end-to-end elapsed time.
