"""Prompt-policy controller clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import ControllerAction


SMALLEST_CONTROLLER_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"


@dataclass(frozen=True)
class ControllerModelConfig:
    model: str = SMALLEST_CONTROLLER_MODEL
    max_new_tokens: int = 30
    temperature: float = 0.7
    top_p: float = 0.9
    device: str = "auto"


class TinyController:
    """Local Hugging Face text-generation wrapper for a tiny controller."""

    def __init__(
        self,
        config: ControllerModelConfig | None = None,
        dry_run: bool = False,
    ) -> None:
        self.config = config or ControllerModelConfig()
        if self.config.max_new_tokens > 30:
            raise ValueError("controller action budget must be 30 generated tokens or fewer")
        self.dry_run = dry_run
        self._pipeline: Any | None = None

    def instruct(self, state: str, sample_index: int = 0) -> str:
        return self.act(state, sample_index=sample_index).instruction

    def act(self, state: str, sample_index: int = 0) -> ControllerAction:
        if self.dry_run:
            instruction = dry_run_instruction(sample_index)
            return ControllerAction(
                instruction=instruction,
                output_tokens=count_simple_tokens(instruction),
                token_budget=self.config.max_new_tokens,
                model=f"{self.config.model}:dry-run",
                raw_text=instruction,
            )

        if self._pipeline is None:
            from transformers import pipeline

            pipeline_kwargs: dict[str, Any] = {
                "task": "text-generation",
                "model": self.config.model,
            }
            if self.config.device != "auto":
                pipeline_kwargs["device"] = self.config.device
            self._pipeline = pipeline(**pipeline_kwargs)

        prompt = build_controller_prompt(state)
        outputs = self._pipeline(
            prompt,
            max_new_tokens=self.config.max_new_tokens,
            do_sample=self.config.temperature > 0,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            return_full_text=False,
        )
        raw_text = outputs[0]["generated_text"]
        instruction = clean_instruction(raw_text)
        return ControllerAction(
            instruction=instruction,
            output_tokens=self.count_tokens(instruction),
            token_budget=self.config.max_new_tokens,
            model=self.config.model,
            raw_text=raw_text,
        )

    def count_tokens(self, text: str) -> int:
        if self._pipeline is not None:
            tokenizer = getattr(self._pipeline, "tokenizer", None)
            if tokenizer is not None:
                tokenized = tokenizer(text, add_special_tokens=False)
                return len(tokenized["input_ids"])
        return count_simple_tokens(text)


def build_controller_prompt(state: str) -> str:
    return (
        "You are a prompt-policy controller. Emit one short instruction, "
        "30 tokens or fewer, to help a frozen math solver answer correctly. "
        "Do not copy problem text, markup, names, or labels.\n\n"
        f"State:\n{state.strip()}\n\nInstruction:"
    )


def clean_instruction(text: str) -> str:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    cleaned = first_line.strip().strip('"').strip("'")
    if is_bad_instruction(cleaned):
        return dry_run_instruction(0)
    words = cleaned.split()
    if len(words) > 30:
        cleaned = " ".join(words[:30])
    return cleaned or dry_run_instruction(0)


def is_bad_instruction(text: str) -> bool:
    lowered = text.lower()
    bad_fragments = ["[/", "[*", "[list", "problem:", "response:", "following in the response"]
    if any(fragment in lowered for fragment in bad_fragments):
        return True
    return len(text.split()) < 3


def dry_run_instruction(sample_index: int = 0) -> str:
    instructions = [
        "Derive the result carefully; finish with only the boxed answer.",
        "Check constraints before algebra; output the final value in boxed form.",
        "Look for invariants and avoid approximation; give one boxed answer.",
    ]
    return instructions[sample_index % len(instructions)]


def count_simple_tokens(text: str) -> int:
    return len(text.split())
