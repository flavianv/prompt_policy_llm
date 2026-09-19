# experiment0.0 — AdaptGym memory

[Full report and nine trace-verified mini cases](report.md) · [Machine-readable cases](cases.json) · [Checksummed manifest](manifest.json)

Fixed Qwen3-1.7B maintains explicit notes; frozen Luna answers preferences after every
session. Ten users × ten sessions: 79.0% with prior notes versus 49.5% without them.
The report separates content mistakes, recovered tool failures, and incorrect Luna
answers despite correct evidence. Original run: `adaptgym_10x10_20260917_v2`.

## Reanalyze saved outputs (offline, no API/GPU)

From the repository root, with Python >=3.9:

```bash
python3 experiments/experiment0.0/reproduce.py
python3 experiments/experiment0.0/reproduce.py --reanalyze --output /tmp/experiment0.0-reanalysis
```

The first command is the default and makes no network calls: it checks file hashes,
regenerates the exact synthetic episodes, reconciles every scored answer against
raw API output, validates editorial extracts, recomputes metrics, and audits temporal
isolation. The second writes derived JSON into a NEW directory. Existing output
paths are rejected. No third-party packages are needed for these offline commands.

## Fresh inference (explicit paid opt-in)

Use Python 3.12 on CUDA hardware compatible with BF16 Qwen3. The recorded direct
runtime pins are in `requirements-runtime.txt`; full installed version inventory
is in `environment.json`. Install in a dedicated environment rather than altering
a shared training environment. No external AdaptGym checkout is required: the exact
MIT-declared source export is under `vendor/adaptgym` with attribution/license notice.

Download Qwen/Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` into a
local model directory. The entrypoint verifies every weight/tokenizer file against
`model_manifest.json` before calling either model. Do not check credentials into Git.

```bash
python experiments/experiment0.0/reproduce.py --real-run \
  --model-path /path/to/Qwen3-1.7B \
  --credentials /private/path/openai.env \
  --output /path/to/new/experiment0.0-rerun
```

On the existing RecoAtlas checkout:

```bash
cd /home/criteo/qwen17b-work/prompt_policy_llm
/home/criteo/verl-venv/bin/python experiments/experiment0.0/reproduce.py --real-run \
  --model-path /home/criteo/qwen17b-work/model \
  --credentials /home/criteo/reco-rl/app/backend/.env \
  --output /home/criteo/qwen17b-work/runs/experiment0.0-fresh
```

This invokes the checksum-pinned original evaluator, including its small Luna and
Qwen smokes, then the exact ten seeds and protocol. It uses existing credentials
without printing or copying them. Weights stay fixed. The original legacy module
is retained byte-for-byte for provenance and itself is a live-run CLI; use this
wrapper for safe default validation.

**Fresh numerical results may differ:** Luna was recorded as an API alias, not an
immutable model snapshot; temperature/seed were unset, and GPU/runtime behavior can
vary. Offline reanalysis reproduces the saved counts exactly. Hash validation is
not a promise that the historical API model remains available.

## Version identity

Implementation commit: `af8e094a662a9e0dbe3a37bec6651ca759f68216`.
The offline wrapper tolerates only 1e-12 floating-point aggregation differences across Python versions; integer counts and categorical outputs must match exactly.

The separate report commit contains this directory's report/evidence/manifest and
pins that code commit; inspect it with `git log -1 -- experiments/experiment0.0/manifest.json`.

The run preceded these commits. Its old HEAD plus dirty source is documented in
`evidence/staged_source_manifest.json`; the actual imported source matches the
pinned implementation bytes. Unrelated uncommitted MovieLens/default changes are
excluded. The original artifacts remain in the ignored `runs/` directories; this
tracked evidence copy removes that dependency. The earlier incomplete harness
attempt is explicitly separate under `evidence/initial-harness`.
