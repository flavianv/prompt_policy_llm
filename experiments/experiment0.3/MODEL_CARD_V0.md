---
base_model: Qwen/Qwen3-4B
library_name: peft
pipeline_tag: text-generation
language:
- en
license: apache-2.0
datasets:
- flavianv/prompt-policy-memory-v0
---
# Qwen3-4B plain-text memory GRPO adapter v0

This is a standard LoRA adapter for the pinned Qwen3-4B base model, not standalone full weights. It was trained for cumulative-session note-taking. The full experiment report below documents training, datasets, evaluation and limitations.

## Loading

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
base_id = "Qwen/Qwen3-4B"
revision = "1cfa9a7208912126459214e8b04321603b3df60c"
tokenizer = AutoTokenizer.from_pretrained(base_id, revision=revision)
base = AutoModelForCausalLM.from_pretrained(base_id, revision=revision, dtype=torch.bfloat16)
model = PeftModel.from_pretrained(base, "flavianv/prompt-policy-memory-grpo-v0")
model.eval()
```

Use the accompanying policy system prompt, Qwen chat template with `enable_thinking=False`, cumulative session text and previous predicted notes. Apply the repository's merge and value-scoring code for exact reproduction. Generate with temperature 1.5, top-p 1 and top-k 0. The training environment used torch 2.11, transformers 5.12.1 and peft 0.19.1.

# Qwen3-4B note-taking GRPO — version 0

## Outcome

GRPO improved mean target-value recall on 100 training sessions from 73.75% to 91.37% in the first matched comparison. Two additional sampling seeds confirmed the gain; the average gain across three seeds was 18.33 percentage points. On 20 sessions from two new users, recall improved from 66.99% to 80.93% (+13.93 points). This small held-out test uses the same generator and templates and does not establish broad generalization.

## Published artifacts

- [Model adapter and model card](https://huggingface.co/flavianv/prompt-policy-memory-grpo-v0)
- [Dataset: 100 train sessions and 20 test sessions](https://huggingface.co/datasets/flavianv/prompt-policy-memory-v0)
- [Code and experiment artifacts](https://github.com/flavianv/prompt_policy_llm/tree/experiment0.0-adaptgym-memory)

Hugging Face repositories are public. The model release contains a LoRA adapter, not a duplicate of the base model. Both dataset splits are in one versioned dataset repository.

## Data and input/output contract

The original training set contains ten synthetic users with ten chronological sessions each. After freezing the trained checkpoint, two fresh profiles were generated with gpt-5.6-luna, with ten sessions each. Profiles and user identities are disjoint. Seeds, raw generation attempts, validation results and file hashes are retained. Session templates and fixed temporal probes are shared between splits.

At session t, the model receives the plain text of sessions 1 through t, timestamps/current time, and its own previously saved notes. Neither future sessions nor private target profiles appear in the prompt. The model emits sparse plain-text facts, one descriptive `key: value` per line. Keys are flexible and a distinctive value may appear alone. There is no JSON output requirement. Existing notes are retained unless an update replaces the same normalized key. Candidate zero is carried to the next session regardless of its reward; there is no best-of-four memory selection.

The dataset provides canonical complete notes for supervised fine-tuning, generated from revealed prefix facts. These references use empty initial memory; they are not the sampled GRPO rollouts. Evaluator target fields are labels and must not be inserted into model inputs.

## Reward and metrics

Training reward is the count of unique normalized values shared by the merged notes and the private current target. Keys are ignored. Repeated values count once; unsupported values do not subtract from reward. Case, punctuation, collection ordering and a small unit-alias table are normalized; ISO dates are preserved. Compound/list values must match as a whole normalized collection.

Primary evaluation averages value recall across four candidates within each session, then across sessions. Exact pass@4 means at least one candidate's entire value set matches the target with no unsupported values. Neither metric establishes correct assignment of values to attributes. We separately retain unsupported-value counts and output validity.

## Training

- Base: Qwen/Qwen3-4B, revision `1cfa9a7208912126459214e8b04321603b3df60c`.
- Hardware: RecoAtlas B200 MIG 3g.90gb; frozen BF16 base and FP32 standard LoRA adapters under BF16 autocast; no quantization.
- LoRA: rank 16, alpha 32, dropout 0; attention q/k/v/o and MLP gate/up/down projections.
- GRPO: four samples per session, temperature 1.5, top-p 1, top-k 0; group-normalized advantages, clip 0.2, KL coefficient 0.02.
- Optimizer: AdamW, learning rate 0.00001, gradient norm cap 1; seed 2718.
- Context limit 16,384 tokens; output cap 8,192 tokens; Qwen thinking disabled.
- One chronological pass over 100 sessions; 16 nonzero learning updates and 84 tied-reward groups skipped.
- Saved adapter reloaded with maximum checked log-probability difference 0.0.
- Training source commit: `bf6422316125c6a8376d5e7da18e3582c9747311`.

## Matched results

The original model is evaluated with the adapter disabled; the trained model uses the saved adapter. Inputs, instructions, temperature, candidate count, scoring and carry policy match. Each model carries its own notes. No updates occur during evaluation.

| Split / seed | Frozen recall | GRPO recall | Gain |
|---|---:|---:|---:|
| Train / 7319 | 73.75% | 91.37% | 17.63 pp |
| Train / 7320 | 72.61% | 91.01% | 18.40 pp |
| Train / 7321 | 72.28% | 91.23% | 18.95 pp |
| New-user test / 7322 | 66.99% | 80.93% | 13.93 pp |

| Test metric across all 80 candidates | Frozen | GRPO |
|---|---:|---:|
| Matched values | 747 | 888 |
| Target values | 1088 | 1088 |
| Unsupported values | 228 | 133 |
| Parseable outputs | 80 | 80 |

Both models achieved exact pass@4 in one of twenty test sessions. Exact individual candidates increased from 2/80 to 4/80. Higher recall therefore does not imply complete or fully precise notes.

## Validation and limitations

All 42 focused CPU tests pass. Metrics were independently recomputed from saved candidate records. Baseline/trained public inputs, target counts and decoding configurations were compared. All 160 held-out outputs were parseable, and the held-out run performed zero training updates.

The first three comparisons reuse training data and must be described as in-sample. Repeated seeds test sampling stability for one checkpoint, not stability across independent training runs. The test has only two users and shares generation templates, schema and temporal anchors with training. Gains partly reflect separating compound status/deadline outputs into independently matchable facts. Value-only scoring can credit incorrectly labeled values, and free-form synonymous keys can preserve stale notes. Unsupported values are reported but are not penalized by the training reward. No hyperparameters were adjusted using the held-out results.

## Reproduction and retained evidence

The code repository includes generation/packaging/evaluation scripts, frozen training source, run configuration, exact sampled traces, aggregate metrics and data hashes under `experiments/experiment0.3/`. `hf_memory_v0/` contains both Hugging Face dataset splits and evaluator fixtures. `cumulative_temp15_run01/` contains the initial comparison, two repeats and held-out results. The remote adapter remains under the completed run's `final_adapter` directory, and its published copy includes SHA-256 hashes. Legacy configuration labels mentioning structured fields are superseded by the recorded run reward and frozen value-intersection implementation.
