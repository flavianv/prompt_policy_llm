"""Lazy local hint providers for deployment-valid controller data collection."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .schema import EvalItem, Generation, Problem


LFM2_350M_MATH_MODEL = "LiquidAI/LFM2-350M-Math"
LFM2_HINT_MODEL_ALIAS = "lfm2-350m-math"
MIN_TRANSFORMERS_VERSION = (4, 55)


@dataclass(frozen=True)
class LocalHintConfig:
    model: str = LFM2_350M_MATH_MODEL
    device: str = "auto"
    max_new_tokens: int = 30
    temperature: float = 0.6
    top_p: float = 0.95
    repetition_penalty: float = 1.05


def resolve_local_hint_model(name: str) -> str:
    if name == LFM2_HINT_MODEL_ALIAS:
        return LFM2_350M_MATH_MODEL
    raise ValueError(f"unsupported local hint model: {name}")


def build_local_hint_prompt(problem: Problem, baseline: EvalItem, candidates: int) -> str:
    """Build a single-turn prompt without trusted answer or baseline answer text."""

    del baseline
    return (
        f"Write exactly {candidates} diverse controller hint lines for the math problem below. "
        "Each line must contain one solving tactic, target 8 to 16 tokens, and never exceed "
        "30 tokens. Do not solve the problem, state any final answer, copy labels, or include "
        "answer-like numbers.\n\n"
        f"Problem:\n{problem.problem}\n\n"
        "Return only the hint lines."
    )


class LocalLFMHintProvider:
    """Run LFM2 locally only when a hint is actually requested."""

    def __init__(self, config: LocalHintConfig | None = None) -> None:
        self.config = config or LocalHintConfig()
        if self.config.max_new_tokens < 1 or self.config.max_new_tokens > 30:
            raise ValueError("local hint max_new_tokens must be between 1 and 30")
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None
        self.runtime_device: str | None = None

    def propose(self, problem: Problem, baseline: EvalItem, candidates: int) -> Generation:
        if candidates < 1:
            raise ValueError("candidates must be at least 1")
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None
        assert self.runtime_device is not None

        prompt = build_local_hint_prompt(problem, baseline, candidates)
        messages = [{"role": "user", "content": prompt}]
        encoded = self._tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.runtime_device)
        input_length = int(encoded["input_ids"].shape[-1])
        started = time.perf_counter()
        with self._torch.inference_mode():
            generated = self._model.generate(
                **encoded,
                do_sample=True,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                repetition_penalty=self.config.repetition_penalty,
                max_new_tokens=self.config.max_new_tokens,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        latency_s = time.perf_counter() - started
        completion = generated[0][input_length:]
        text = self._tokenizer.decode(completion, skip_special_tokens=True).strip()
        return Generation(
            text=text,
            latency_s=latency_s,
            input_tokens=input_length,
            output_tokens=int(completion.shape[-1]),
            cost_usd=0.0,
            model=f"{self.config.model}@{self.runtime_device}",
            status="completed",
        )

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            import transformers
            from packaging.version import Version
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Local LFM2 hints require torch and transformers>=4.55. "
                "Install with `pip install -e '.[local-hints]'`."
            ) from exc
        if Version(transformers.__version__) < Version("4.55"):
            raise RuntimeError(
                f"Local LFM2 hints require transformers>=4.55; found {transformers.__version__}. "
                "Install with `pip install -e '.[local-hints]'`."
            )
        device = self._resolve_device(torch)
        dtype = torch.float16 if device == "mps" else (torch.bfloat16 if device == "cuda" else torch.float32)
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.config.model)
            model = AutoModelForCausalLM.from_pretrained(self.config.model, torch_dtype=dtype)
            model.to(device)
            model.eval()
        except Exception as exc:
            raise RuntimeError(
                f"Unable to load local hint model {self.config.model}. "
                "Check network/model access and the local Transformers installation."
            ) from exc
        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch
        self.runtime_device = device

    def _resolve_device(self, torch: Any) -> str:
        if self.config.device != "auto":
            if self.config.device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("Requested local hint device cuda is unavailable.")
            if self.config.device == "mps" and not torch.backends.mps.is_available():
                raise RuntimeError("Requested local hint device mps is unavailable.")
            if self.config.device not in {"cpu", "cuda", "mps"}:
                raise ValueError("local hint device must be auto, cpu, cuda, or mps")
            return self.config.device
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
