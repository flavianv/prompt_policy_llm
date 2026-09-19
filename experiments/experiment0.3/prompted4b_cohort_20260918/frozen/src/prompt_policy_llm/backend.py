"""Frozen back-end model clients."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .schema import Generation


LUNA_INPUT_USD_PER_MTOK = 0.20
LUNA_OUTPUT_USD_PER_MTOK = 1.20
THINK_MODE_CHOICES = ("none", "minimal", "low", "medium", "high", "xhigh")


def estimate_luna_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimate GPT-5.6 Luna cost from official per-million-token prices."""

    return (
        input_tokens * LUNA_INPUT_USD_PER_MTOK / 1_000_000
        + output_tokens * LUNA_OUTPUT_USD_PER_MTOK / 1_000_000
    )


@dataclass(frozen=True)
class LunaConfig:
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "none"
    max_output_tokens: int = 4096
    temperature: float | None = None
    show_work: bool = False


class LunaBackend:
    """OpenAI Responses API wrapper for the frozen Luna back end."""

    def __init__(self, config: LunaConfig | None = None, dry_run: bool = False) -> None:
        self.config = config or LunaConfig()
        self.dry_run = dry_run
        self._client: Any | None = None

    def generate(self, problem: str, instruction: str | None = None) -> Generation:
        if self.dry_run:
            return self._dry_generate(problem, instruction)

        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()

        system = build_solver_system_prompt(show_work=self.config.show_work)
        user = build_luna_prompt(problem, instruction, show_work=self.config.show_work)
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_output_tokens": self.config.max_output_tokens,
        }
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        if self.config.reasoning_effort != "none":
            kwargs["reasoning"] = {"effort": self.config.reasoning_effort}

        started = time.perf_counter()
        response = self._client.responses.create(**kwargs)
        latency_s = time.perf_counter() - started

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cost_usd = estimate_luna_cost(input_tokens, output_tokens)
        text = extract_response_text(response)
        status = str(getattr(response, "status", "") or "")
        incomplete_details = getattr(response, "incomplete_details", None)
        incomplete_reason = str(getattr(incomplete_details, "reason", "") or "")

        return Generation(
            text=text,
            latency_s=latency_s,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model=self.config.model,
            status=status,
            incomplete_reason=incomplete_reason,
        )

    def _dry_generate(self, problem: str, instruction: str | None = None) -> Generation:
        del problem
        answer = "1" if instruction else "0"
        if self.config.show_work:
            text = f"Dry run derivation. Therefore, the final answer is \\boxed{{{answer}}}."
        else:
            text = f"Dry run response. Final answer: \\boxed{{{answer}}}."
        prompt_tokens = 200 + len((instruction or "").split())
        output_tokens = len(text.split())
        return Generation(
            text=text,
            latency_s=0.0,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_luna_cost(prompt_tokens, output_tokens),
            model=f"{self.config.model}:dry-run",
            status="completed",
            incomplete_reason="",
        )


def build_solver_system_prompt(show_work: bool = False) -> str:
    if show_work:
        return (
            "You solve olympiad math problems. Give a concise, verifiable derivation "
            "of the solution, then end with the final answer in \\boxed{}."
        )
    return "You solve olympiad math problems. Return the final answer in \\boxed{}."


def build_luna_prompt(
    problem: str,
    instruction: str | None = None,
    show_work: bool = False,
) -> str:
    prompt = ""
    if instruction:
        prompt += f"Controller instruction: {instruction.strip()}\n\n"
    prompt += "Problem:\n"
    prompt += problem.strip()
    if show_work:
        prompt += "\n\nGive a concise derivation, then end with only one final answer in \\boxed{}."
    else:
        prompt += "\n\nReturn only the final answer in \\boxed{}. Do not include explanation."
    return prompt


def resolve_reasoning_effort(
    reasoning_effort: str,
    think_mode: str | None = None,
) -> str:
    """Use the explicit think mode when supplied, retaining the legacy flag."""

    resolved = think_mode if think_mode is not None else reasoning_effort
    if resolved not in THINK_MODE_CHOICES:
        raise ValueError(f"unsupported reasoning effort: {resolved}")
    return resolved


def extract_response_text(response: object) -> str:
    text = getattr(response, "output_text", "")
    if text:
        return str(text)

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            content_text = getattr(content, "text", None)
            if content_text:
                chunks.append(str(content_text))
    return "\n".join(chunks)
