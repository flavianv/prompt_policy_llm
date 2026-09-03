"""SFT entrypoint for the tiny prompt-policy controller."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .controller import SMALLEST_CONTROLLER_MODEL
from .training_data import load_chat_rows, split_prompt_and_completion


@dataclass(frozen=True)
class TokenizedExample:
    input_ids: list[int]
    attention_mask: list[int]
    labels: list[int]


def main() -> None:
    args = parse_args()
    rows = load_chat_rows(args.train_file)
    print(f"Loaded {len(rows)} controller SFT rows from {args.train_file}")

    if args.dry_run:
        print("Dry run requested; data format is valid and no model was loaded.")
        return

    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    tokenized = [
        tokenize_row(row, tokenizer=tokenizer, max_length=args.max_length)
        for row in rows
    ]
    print(f"Tokenized {len(tokenized)} rows with max_length={args.max_length}")

    if args.validate_only:
        lengths = [len(example.input_ids) for example in tokenized]
        print(f"Validation only; token lengths min={min(lengths)} max={max(lengths)}")
        return

    model_kwargs = {}
    if args.bf16:
        import torch

        model_kwargs["torch_dtype"] = torch.bfloat16
    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs)
    model.resize_token_embeddings(len(tokenizer))

    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_total_limit=2,
        bf16=args.bf16,
        report_to=[],
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ControllerSftDataset(tokenized),
        data_collator=ControllerDataCollator(tokenizer.pad_token_id),
    )
    trainer.train()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))


def tokenize_row(row: dict[str, object], tokenizer, max_length: int) -> TokenizedExample:
    prompt, completion = split_prompt_and_completion(row)
    full_text = prompt + completion + (tokenizer.eos_token or "")
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    encoded = tokenizer(
        full_text,
        add_special_tokens=False,
        truncation=True,
        max_length=max_length,
    )
    input_ids = list(encoded["input_ids"])
    attention_mask = list(encoded["attention_mask"])
    labels = input_ids.copy()
    masked = min(len(prompt_ids), len(labels))
    labels[:masked] = [-100] * masked
    return TokenizedExample(
        input_ids=input_ids,
        attention_mask=attention_mask,
        labels=labels,
    )


class ControllerSftDataset:
    def __init__(self, examples: list[TokenizedExample]) -> None:
        self.examples = examples

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, list[int]]:
        example = self.examples[index]
        return {
            "input_ids": example.input_ids,
            "attention_mask": example.attention_mask,
            "labels": example.labels,
        }


class ControllerDataCollator:
    def __init__(self, pad_token_id: int) -> None:
        self.pad_token_id = pad_token_id

    def __call__(self, features: list[dict[str, list[int]]]) -> dict[str, object]:
        import torch

        max_len = max(len(feature["input_ids"]) for feature in features)
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for feature in features:
            pad = max_len - len(feature["input_ids"])
            batch["input_ids"].append(feature["input_ids"] + [self.pad_token_id] * pad)
            batch["attention_mask"].append(feature["attention_mask"] + [0] * pad)
            batch["labels"].append(feature["labels"] + [-100] * pad)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in batch.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("models/smollm2_135m_controller_sft"))
    parser.add_argument("--model", default=SMALLEST_CONTROLLER_MODEL)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--num-train-epochs", type=float, default=1.0)
    parser.add_argument("--per-device-train-batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--logging-steps", type=int, default=10)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()

