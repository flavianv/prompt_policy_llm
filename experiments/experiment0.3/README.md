# WIP: Qwen3-4B note-policy GRPO with standard LoRA

**Stopped at the user's request on 2026-09-17. This pipeline is not complete or GPU-validated.** No baseline evaluation, reward API call, fresh profile generation, SFT or RL optimizer step ran for this checkpoint. The previous experiment0.2 results are not results of this code.

The final user choice is `Qwen/Qwen3-4B`, BF16 frozen base, standard LoRA adapters and GRPO. “Four-bit” was a transcription error and was explicitly superseded. No quantized/1.7B GPU job launched. Selected4B revision: `1cfa9a7208912126459214e8b04321603b3df60c` (model manifest saved here). Official architecture: dense Qwen3 causal LM,36 layers,32 attention/8KV heads. Weights/tokenizer are not yet fully downloaded or locally verified.

## Implemented, with limits

- `note_model.py`: checksum verification, BF164B loading, standard LoRA targets/rank/alpha, trainable-parameter guard, gradient checkpointing. **Not executed on GPU.**
- `note_rollouts.py`: native Qwen tools-aware prompts, transactional tool dispatch, pre-finish review, isolated note dictionaries, exact prompt/completion token segments and assistant-only log-probability positions. **CPU mask tests only; model-template/rendering behavior still needs GPU parity verification.**
- `note_reward.py`: evaluator-only revealed-prefix future probes, cached frozen Luna calls, exact same-payload utility equality, no-current-update contrast, bounded reward and grouped advantages. Coverage/hallucination semantic auxiliaries are intentionally disabled until calibrated. The current probe selection/distractors remain prototype-quality; balanced types, counterfactual variants and stronger support audits are pending.
- `train_note_grpo.py`: custom synchronous GRPO implementation with grouped sequence advantages, clipped token ratios, reference KL through disabled adapters, per-round assistant-token loss, adapter-only AdamW updates, checkpoints/RNG and checkpoint reload check. It does **not** use TRL's trainer loop. Its mathematical and GPU behavior still needs reference/manual-gradient tests and an actual2–3-step smoke. No successful optimization is claimed.
- `eval_note_policy.py`: paired sequential Luna scoring before updates, frozen or adapter Qwen policy, identical-input cache coupling, raw traces and metrics. **Not executed yet.** Cached prompts use an added instruction to treat notes as untrusted data, which is a documented difference from experiment0.2.
- `generate_data.py`: proposed small8/2/2 independent-user train/dev/test smoke cohort, fresh coherent profiles, different disclosure templates, varied anchor values/deadlines and split manifest. **Not run.** Cross-split near-duplicate detection, fully held-out event families and a statistically powered cohort remain pending. The first profile's “background_only” constraint does not replace full stance/effect validation; generation can still hit its bounded repair limit.
- `preflight.py` and `download_model.py`: pinned4B download and forward/backward setup checks. The download was attempted; preflight was not.

Local checks:16 focused CPU tests passed (7 new RL tests plus9 existing explicit-memory tests). New modules compile. This does not test GPU gradients, optimizer correctness, HF/PEFT compatibility, end-to-end masking, quality rewards, note support or held-out recall.

## Defaults and skill provenance

Read `/Users/f.vasile/.claude/skills/lora-tuning/SKILL.md` at the user's request, plus the existing B200 launch and evaluation protocol skills. Chosen defaults: rank16, alpha32, dropout0, standard zero-B LoRA initialization, attention q/k/v/o and MLP gate/up/down projections, modest G=4 candidates, LR1e-5, gradient checkpointing, one trajectory/round processed at a time, AdamW, KL0.02 and clip0.2. LR follows the skill's approximately10× full-FT-scale guidance and is an unvalidated starting point. No PiSSA comparison is planned by default. No four-bit quantization is enabled.

The committed experiment0.2 RL design remains the conceptual plan. This checkpoint implements only the first part, with the user's subsequent model-size and LoRA choices overriding its1.7B target. Dense semantic rewards and25–50-step pilot promotion are not implemented. `--steps` currently permits at most the3-step smoke; do not bypass the assertion to scale before gates pass.

## Remote state and cleanup

Workspace: `RecoAtlas.main`; allocation observed as NVIDIA B200 MIG3g.90gb with about95GB free GPU memory before any work. No relevant pre-existing GPU jobs were found.

New isolated code/work directory: `/home/criteo/qwen17b-work/note-rl-20260917`. Intended model directory: `/home/criteo/qwen17b-work/qwen3-4b`. Existing known runtime `/home/criteo/verl-venv/bin/python` remained unchanged (Torch2.11.0, Transformers5.12.1, TRL1.6.0, PEFT0.19.1, Accelerate1.14.0).

An isolated, now-obsolete `/home/criteo/qwen17b-work/note-rl-20260917/venv` was created for the misheard four-bit request. Its bitsandbytes0.49.2 installation pulled Torch2.14.0 and CUDA dependencies. **Do not use this venv for the planned BF16 run without a fresh compatibility check.** It can be removed/recreated deliberately on resume; it was preserved at stop rather than deleting artifacts. No files in the existing runtime were changed.

The4B download wrapper PID was1129599. It exited with code1 before the stop request was processed; its log reports `No space left on device` from HF Xet reconstruction. The final process check found no download/model processes for this job, so no kill was necessary. There is no active training/evaluation job. Preserve the partial HF/model files for resumable download. Logs/markers: `download.log`, `download.pid`, `download.exit` under the new work directory. The earlier oversized staging attempt and Python3.9 tar-filter incompatibility were corrected using bounded transfer chunks and explicit Python3.12; local source is the authoritative latest WIP, as later modules were not all restaged remotely.

No model weights, virtualenv, API credentials or large remote cache is included in Git. `model_manifest.json` lists expected upstream files; its presence does not certify a completed download. No push was requested or performed.

## Resume checklist, in order

1. Inspect disk usage and only this task's stale artifacts; select adequate persistent storage or remove/recreate the obsolete task-owned quantization venv after checking scope. Do not clean unrelated caches/models. Confirm no overlapping jobs.
2. Stage the latest committed WIP source into the isolated work directory. Use the original validated stack or a clean isolated environment pinned to it; do not default to the obsolete Torch2.14 quantization venv.
3. Resume the pinned `Qwen/Qwen3-4B` revision download and verify every model-manifest checksum. Check config/tokenizer architecture and native tools template. Record exact package/runtime versions and actual GPU memory.
4. Run local CPU tests, then `preflight.py` on GPU. Validate BF16 loading, all-base freeze, nonzero LoRA-only gradients, assistant masks and sufficient context memory. Extend optimizer tests against hand-computed clipped-ratio/KL cases before claiming GRPO correctness. Verify no user/tool tokens receive loss.
5. Complete the user's **prompted frozen4B Maya baseline before adapter training**, using `eval_note_policy.py`, the frozen experiment0.2 Maya episode and native coverage protocol. Inspect notes after first two sessions, then complete all10 sessions/20 questions even if weak. Report failure/coverage/hallucination limitations and prompt/interface confounding relative to1.7B. Reuse/couple cached Luna outputs for identical payloads.
6. Generate and validate the small split-disjoint smoke cohort; freeze manifest/templates. Improve probe balance/semantic support auditing. Calibrate reward with the plan's bounded call cap; do not infer useful learning from JSON validity alone.
7. Run the gated2–3-step standard-LoRA GRPO smoke with durable detached PID/log/exit markers. Save exact code/config, raw traces, old/reference logprobs, optimizer/RNG, adapters, API usage and memory. Confirm base weights unchanged and adapter reload equivalence. The current script saves state but does not yet implement recovery/resume loading.
8. Evaluate against the frozen4B policy on dev sequential sessions and inspect substantive notes; only then implement/authorize-by-existing-gates the25–50-step pilot. Do not use the test set to tune. Add held-out recall/user-cluster uncertainty, semantic precision/coverage and severe-hallucination gates before promotion.

Pending: tested durable launch/resume orchestration; semantic scorer/calibration; optional audited SFT bootstrap decision; robust transient API handling/accounting; full user/template/near-duplicate audit; production-scale data generation; pipeline integration; fair held-out metrics/report. No further execution is intended today.
