---
language:
- en
task_categories:
- text-generation
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
  - split: test
    path: data/test.jsonl
---
# Prompt Policy Memory v0

Synthetic profile-memory data: **100 training sessions from10users;20test sessions from2fresh users**. Test users were generated after the GRPO checkpoint was frozen and must not be used for training or tuning.

Each row includes cumulative plain-text session input, a canonical plain-text key:value reference, chat messages, and evaluator-only target data. `messages` can be used for supervised fine-tuning. The reference contains all currently revealed facts; it does not inject gold previous notes. The GRPO runtime instead carries its own predicted notes and emits sparse updates.

## Fields

- `prompt`: raw chronological sessions1..t with timestamps and empty initial notes; no future statements or profile JSON.
- `completion`: deterministic canonical full notes, one descriptive key:value per line.
- `messages`: system, user prompt, assistant reference.
- `target_profile_json`, `target_value_signatures`, `target_value_count`: evaluator labels; never add them to model input.
- `user_id`, `session_index`, `profile_sha256`: grouping and provenance.

## Evaluation

The user-selected reward counts unique normalized values in the intersection of notes and targets, ignoring keys. Case, punctuation, collection order and a small unit-alias table are normalized; ISO dates remain intact. This measures value recall, not correct attribute assignment. Duplicate values count once. Unsupported values do not reduce reward; report their count and value precision separately.

The public train split is already used by one BF16 Qwen3-4B LoRA GRPO run. The test split contains new Luna-generated coherent profiles and new deterministic session seeds. It shares the original schema, templates and fixed temporal probes, so it is a same-generator unseen-user test, not an independent-domain benchmark.

## Reproduction and provenance

`profiles/` contains synthetic full profiles for reproducibility. `evaluation_data/` separates public observations from private prefix targets. `provenance.json` records user separation and hashes. Keep all sessions of a user in the same split. The dataset contains no real user records.
