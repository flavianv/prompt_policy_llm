# Qwen 4B GRPO: cumulative plain-text notes

Matched evaluation seeds completed: 3. Temperature1.5; four candidates per session;100sessions;16optimizer updates.

Input: raw sessions1..t plus own saved notes. Output: sparse plain-text key:value lines with flexible/optional keys. Reward: number of unique normalized values intersecting the private current-profile target. Candidate0 carries memory independently of reward.

| Seed | Frozen recall | Trained recall | Gain | Frozen pass@4 | Trained pass@4 |
|---|---:|---:|---:|---:|---:|
| 7319 | 73.75% | 91.37% | +17.63 pp | 12/100 | 20/100 |
| 7320 | 72.61% | 91.01% | +18.40 pp | 9/100 | 19/100 |
| 7321 | 72.28% | 91.23% | +18.95 pp | 12/100 | 22/100 |

The primary recall averages the four candidates within each session, then averages100sessions. Raw totals below count all400candidates (not candidate0 and not averages divided by a single-trace denominator).

| Seed / phase | Matched / target values | Value precision | Unsupported values | Valid outputs |
|---|---:|---:|---:|---:|
| 7319 / baseline | 4252/5692 | 82.24% | 918 | 400/400 |
| 7319 / trained | 5196/5692 | 93.15% | 382 | 400/400 |
| 7320 / baseline | 4171/5692 | 82.06% | 912 | 400/400 |
| 7320 / trained | 5172/5692 | 92.70% | 407 | 400/400 |
| 7321 / baseline | 4146/5692 | 81.65% | 932 | 400/400 |
| 7321 / trained | 5186/5692 | 93.36% | 369 | 400/400 |

## Per-user mean paired gain

| User | Gain averaged across seeds |
|---|---:|
| user01 | +15.57 pp |
| user02 | +28.89 pp |
| user03 | +29.03 pp |
| user04 | +0.49 pp |
| user05 | +27.97 pp |
| user06 | +26.94 pp |
| user07 | +23.53 pp |
| user08 | +1.33 pp |
| user09 | +29.44 pp |
| user10 | +0.05 pp |

## Interpretation

The first matched comparison improved66sessions, tied31, and worsened3. Gains are concentrated in separately matchable purchase-intent statuses/deadlines; this includes improved output formatting, not just newly recovered information.

All42CPUchecks passed. Actual adapter changes were measured on16updates; checkpoint reload maximum log-probability error was0. Source/config receipts and exact candidate traces accompany this report. Repeated evaluations reuse the same checkpoint without further learning.

## Limitations

- All100sessions used for training; in-sample only.

- Reward is unique normalized value intersection; keys and attribute assignment are ignored.

- Unsupported values do not reduce reward.

- Repeated seeds measure sampling stability for one trained checkpoint, not retraining stability.

- Bootstrap uses ten users sharing generator templates; no held-out generalization claim.

## Artifacts

- `run/comparison.json`, `run/training_summary.json`, `run/training_metrics.jsonl`
- `run/baseline/` and `run/trained/`: all exact input/output traces
- `repeat_seed_*/`: repeated matched traces and metrics
- `source_receipt.json`, `artifact_hashes.json`, `frozen_source/`: provenance
- Remote checkpoint: `/home/criteo/qwen17b-work/cumulative-temp15-20260918/all100_01/run/final_adapter` (weights excluded from git).
