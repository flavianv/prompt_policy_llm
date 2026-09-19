# Frozen prompted Qwen3-4B + Luna: partial cohort review

Primary requested review: **3/10 users**, 30/100 sessions and 60/200 questions. Partial cohort by user request; evaluation stopped. No training or adapters. Reports below contain every completed user’s ten sessions, full statements, notes before/after, both decisions and raw tool calls.

[Exact frozen prompts/settings](PROMPTS.md) · [Aggregate machine-readable results](aggregate.json)

## Computed logs available independently of review

[Maya session log](results/user01/SESSION_LOG.md) · [Evan session log](results/user02/SESSION_LOG.md) · [Aiko session log](results/user03/SESSION_LOG.md). These deterministic logs contain exact prompts/settings, full current statements, prior/updated notes, tool actions/results, choices, answers, evaluator-only gold, scores and note diffs/sizes. They contain no semantic-review narrative. Existing logs were rebuilt from saved JSON; the evaluator now calls the same renderer after each completed session for future runs. This logging-only change was made after the stopped run; the original executed sources remain frozen and hashed under frozen/. No model was rerun.

Rebuild a log from the repository root: `PYTHONPATH=src python3 -m prompt_policy_llm.note_eval_log experiments/experiment0.3/prompted4b_cohort_20260918/results/user01`. Rebuild the review index/reports: `PYTHONPATH=src python3 experiments/experiment0.3/report_prompted_cohort.py experiments/experiment0.3/prompted4b_cohort_20260918 --max-users 3`.

| User | Luna only | With prior notes | Delta correct | Finalized sessions | Invalid tool rounds | Report |
|---|---:|---:|---:|---:|---:|---|
| Maya Okafor | 10/20 | 19/20 | +9 | 10/10 | 0/42 | [user01](results/user01/REPORT.md) |
| Evan Mercer | 15/20 | 20/20 | +5 | 10/10 | 0/40 | [user02](results/user02/REPORT.md) |
| Aiko Nakamura | 9/20 | 16/20 | +7 | 10/10 | 0/42 | [user03](results/user03/REPORT.md) |

## Actual stop state

The stop request reduced the review to the first three users. At receipt, users01–04 had already completed and user05 had eight completed sessions: **48 sessions / 96 scored questions actually executed**. The evaluator process group was terminated immediately. Only users01–03 enter the primary results below; extra pre-stop output remains intact in [user04 raw results](results/user04/) and [user05 partial raw results](results/user05/). No subsequent run was launched. [Stop receipt](user_requested_stop.json).

## Note quality: final current-state fields

| User | Supported | Ambiguous | Incorrect | Missing | Total fields |
|---|---:|---:|---:|---:|---:|
| Maya Okafor | 18 | 1 | 1 | 3 | 23 |
| Evan Mercer | 15 | 1 | 0 | 4 | 20 |
| Aiko Nakamura | 13 | 0 | 1 | 8 | 22 |

These are manual single-reviewer judgments over final revealed fields, separate from question accuracy. The reports document intermediate forgetting, missing history, scope errors and filler. They do not estimate exhaustive hallucination precision/recall.

## Findings

For the requested three users, prior notes raised accuracy from **34/60 (56.7%) to55/60 (91.7%)**, a35-percentage-point increase:22 memory-only wins,1 baseline-only win,33 both-correct and4 both-wrong. Earlier-session questions improved20/46→41/46; historical questions5/11→10/11; current-session questions were14/14 for both arms. These are descriptive results on this fixed synthetic cohort, without statistical generalization.

Maya:10/20→19/20; missed completed intent caused the remaining error. Evan:15/20→20/20 despite four missing final fields and ambiguous shirt-pattern history. Aiko:9/20→16/20; temporary restoration was misanswered even when baseline notes existed, languages were omitted, historical hat occasions were overwritten, and shirt brands were later forgotten. The sole paired regression was Aiko session5: baseline selected the correct historical hat occasion, while notes led to the newer value.

All124 tool calls were valid and all30 note sessions finalized; no generated call hit its768-token output cap. Nevertheless, final-note field review found46/65 supported,15 missing,2 ambiguous and2 incorrect. This manual current-state audit is separate from complete historical coverage. Examples: Maya changed a deadline by nine minutes and retained three irrelevant statements; Evan dropped a cancelled intent; Aiko deleted several prior facts and misbound an unknown update to the word travel.

The first three users took273.08s total evaluation wall time:125.99s Qwen generation and146.60s Luna API wait. Final notes were206,132 and131 words respectively, all one entry and well below the1600-word budget. Aiko shrank145→84 words in session7 while losing facts. The run used serial interleaving; two-phase bounded-concurrent Luna execution is valid for a future run but was not implemented after the stop request.

## Aggregate


```json
{
  "review_users_requested": 3,
  "users_complete": 3,
  "sessions": 30,
  "questions": 60,
  "note_quality": {
    "total": 65,
    "supported": 46,
    "ambiguous": 2,
    "incorrect": 2,
    "missing": 15,
    "users_reviewed": 3,
    "unit": "Unique revealed current-state field in final notes; manual single-reviewer audit, not question accuracy or complete history coverage."
  },
  "stop_state": {
    "requested_users": 3,
    "reason": "User requested stop after first three; no further evaluation authorized",
    "observed_at_stop": [
      {
        "user": "user01",
        "sessions": 10,
        "questions_scored": 20,
        "complete": true
      },
      {
        "user": "user02",
        "sessions": 10,
        "questions_scored": 20,
        "complete": true
      },
      {
        "user": "user03",
        "sessions": 10,
        "questions_scored": 20,
        "complete": true
      },
      {
        "user": "user04",
        "sessions": 10,
        "questions_scored": 20,
        "complete": true
      },
      {
        "user": "user05",
        "sessions": 8,
        "questions_scored": 16,
        "complete": false
      }
    ],
    "time": 1789723461.7613437,
    "verified_no_remaining_processes": true
  },
  "overall": {
    "questions": 60,
    "baseline": {
      "correct": 34,
      "accuracy": 0.5666666666666667,
      "invalid": 0
    },
    "memory": {
      "correct": 55,
      "accuracy": 0.9166666666666666,
      "invalid": 0
    }
  },
  "earlier_session_evidence": {
    "questions": 46,
    "baseline": {
      "correct": 20,
      "accuracy": 0.43478260869565216,
      "invalid": 0
    },
    "memory": {
      "correct": 41,
      "accuracy": 0.8913043478260869,
      "invalid": 0
    }
  },
  "current_session_evidence": {
    "questions": 14,
    "baseline": {
      "correct": 14,
      "accuracy": 1.0,
      "invalid": 0
    },
    "memory": {
      "correct": 14,
      "accuracy": 1.0,
      "invalid": 0
    }
  },
  "historical": {
    "questions": 11,
    "baseline": {
      "correct": 5,
      "accuracy": 0.45454545454545453,
      "invalid": 0
    },
    "memory": {
      "correct": 10,
      "accuracy": 0.9090909090909091,
      "invalid": 0
    }
  },
  "paired": {
    "memory_only": 22,
    "baseline_only": 1,
    "both_correct": 33,
    "both_wrong": 4
  },
  "note_rounds": 124,
  "invalid_note_rounds": 0,
  "note_sessions_finished": 30,
  "api_calls_this_process": 57,
  "cache_hits": 3,
  "wall_seconds": 273.08484877389856
}
```


## Interpretation limits

Paired accuracy measures usefulness of prior Qwen notes on these fixed questions. Factual support, omissions and hallucinations require the separate note-quality review; protocol validity alone cannot establish them. This is a small synthetic cohort, and the earlier1.7B runs differ in prompt/interface and caching, so their differences are confounded.
