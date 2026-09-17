# Explicit-state memory checkpoint

Completed dataset: [dataset_v1/README.md](dataset_v1/README.md), ten actual Luna-generated coherent profiles, 100 sessions, 200 questions, 809 statements. Each user has one profile containing general facts and all clothing categories; sessions reveal subsets and apply explicit state updates. Generation concurrency was three; the initial nine-user batch took 99.58 seconds, excluding the later single-profile repair. Every profile needed two attempts; user05 needed a third targeted repair. All raw calls and validation outcomes are saved.

Maya paired live smoke: [report](remote_artifacts/live_evaluation/REPORT.md). Current-session Luna 8/20, designated memory arm10/20, but Qwen failed all120 note-tool calls and stored nothing. All ten arm payloads were identical. This is a protocol failure, not evidence of memory improvement. Only Maya was evaluated; no weight training occurred. Her final dataset episode exactly matches the evaluated episode.

The original failed run and its executed source snapshot remain in `remote_artifacts/`. A separate native Qwen tool-interface repair was checked with two bounded first-session smokes, without additional Luna answer calls. It stored one real scoped preference but omitted most facts; see [note-interface report](NOTE_INTERFACE_REPORT.md). It does not overwrite the failed comparison.

## Reproduce offline checks

```sh
PYTHONPATH=src python3 -m pytest tests/test_profile_contract.py tests/test_explicit_memory.py -q
python3 experiments/experiment0.2/audit_run.py experiments/experiment0.2/remote_artifacts/live_evaluation
python3 experiments/experiment0.0/reproduce.py --validate
```

`generate_cohort.py` makes bounded external profile calls and requires configured credentials. `finalize_dataset.py` rebuilds a new dataset directory from preserved profile outputs and verifies state/repetition consistency; it refuses to overwrite an existing dataset. `audit_run.py` makes no external calls.

Profile contract: `../experiment0.1/profile_generation/user_profile.schema.json` and its category definitions. `null` explicitly means unknown; `[]` means no stated preference; omitted scoped keys inherit defaults. Known but unrevealed fields never enter model observations. Default size never implies brand size or conversion. Scoped preferences inherit defaults and apply matching overrides from least to most specific; later array entries break equal-specificity ties.

The schema validator covers this shipped schema, not arbitrary JSON Schema. Conditional profile generation checks exact fixed nested values, arrays and JSON Pointer constraints. Names/demographics are synthetic; no personal trait or preference is inferred by the evaluator.

The seeded session generator creates natural-language template statements, not free-form LLM conversations. It separates hidden initial state, revealed timestamped state, current/historical queries, and evaluator-only answer keys. Temporary overrides expire into the prior base; intent deadlines are inclusive. Repetition, unrelated filler, third-person comments and product descriptions do not mutate state. Statement counts are configurable6–10; two questions/session is a default within the requested1–2 range. The first two gaps are controlled5-day probes; later gaps are seeded.

Preserved earlier samples in `dataset/` and experiment0.1 are exploratory snapshots. Use `dataset_v1/` for the complete validated cohort. Experiment0.0 is unchanged.

Validation: full local suite80 passed,1 skipped; experiment0.0 offline replay passed; live Maya trace audit passed; all ten profiles and200 answer keys validated.

A later user-authorized coverage-focused repair tested two sessions with a mandatory model review before finishing. It saved more first-session facts but introduced unsupported details and ignored session2 updates. The substantive gate failed; no paired rerun. See [coverage repair report](remote_artifacts/note_coverage_v3/REPORT.md).
