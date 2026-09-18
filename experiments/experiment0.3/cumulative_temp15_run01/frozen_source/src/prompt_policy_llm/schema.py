"""Shared dataclasses for prompt-policy evaluation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    id: str
    problem: str
    answer: str
    domain: str = ""
    difficulty: float | None = None
    source: str = ""


@dataclass(frozen=True)
class Generation:
    text: str
    latency_s: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    status: str = ""
    incomplete_reason: str = ""


@dataclass(frozen=True)
class ControllerAction:
    instruction: str
    output_tokens: int
    token_budget: int
    model: str
    raw_text: str = ""

    @property
    def over_budget(self) -> bool:
        return self.output_tokens > self.token_budget


@dataclass(frozen=True)
class EvalItem:
    problem: Problem
    mode: str
    instruction: str | None
    response: str
    extracted_answer: str
    score: float
    latency_s: float
    backend_latency_s: float
    controller_latency_s: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    generation_status: str = ""
    incomplete_reason: str = ""
    controller_model: str = ""
    controller_output_tokens: int = 0
    controller_token_budget: int = 0
    controller_over_budget: bool = False
    sample_index: int = 0

    @property
    def controller_state(self) -> str:
        lines = [
            "benchmark: omni-math-rule",
            f"domain: {self.problem.domain or 'unknown'}",
            f"difficulty: {self.problem.difficulty if self.problem.difficulty is not None else 'unknown'}",
            "problem:",
            self.problem.problem,
        ]
        return "\n".join(lines)

    @property
    def metadata(self) -> dict[str, object]:
        return {
            "problem_id": self.problem.id,
            "source": self.problem.source,
            "domain": self.problem.domain,
            "difficulty": self.problem.difficulty,
            "expected_answer": self.problem.answer,
            "extracted_answer": self.extracted_answer,
            "mode": self.mode,
            "sample_index": self.sample_index,
            "model": self.model,
            "generation_status": self.generation_status,
            "incomplete_reason": self.incomplete_reason,
            "controller_model": self.controller_model,
            "controller_output_tokens": self.controller_output_tokens,
            "controller_token_budget": self.controller_token_budget,
            "controller_over_budget": self.controller_over_budget,
            "latency_s": self.latency_s,
            "backend_latency_s": self.backend_latency_s,
            "controller_latency_s": self.controller_latency_s,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
        }

    def to_json(self) -> dict[str, object]:
        return {
            **self.metadata,
            "instruction": self.instruction,
            "response": self.response,
            "score": self.score,
        }
