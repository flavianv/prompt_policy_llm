"""Compare direct Luna reasoning with an answer-aware plan/critic oracle pipeline."""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .answer import exact_match_score, normalize_answer
from .backend import (
    THINK_MODE_CHOICES,
    LunaBackend,
    LunaConfig,
    estimate_luna_cost,
    extract_response_text,
    resolve_reasoning_effort,
)
from .datasets import OMNI_MATH_RULE_URL, load_omni_math_rule
from .evaluation import evaluate_one
from .schema import Generation, Problem


DEFAULT_FAILURE_IDS = (
    "HMMT_11:620",
    "HMMT_2:1320",
    "fermat:885",
    "HMMT_11:510",
    "HMMT_2:1199",
)


@dataclass(frozen=True)
class RoleConfig:
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "low"
    max_output_tokens: int = 512


@dataclass(frozen=True)
class TextCheck:
    accepted: bool
    reason: str
    display_text: str


@dataclass(frozen=True)
class CriticEvaluation:
    accepted: bool
    reason: str
    rating: int | None
    failure_category: str | None
    repair: str


class RoleProtocol(Protocol):
    def generate(self, system: str, user: str) -> Generation:
        ...


class LunaRoleClient:
    """Small Responses API client for plan and critic roles."""

    def __init__(self, config: RoleConfig | None = None, dry_run: bool = False) -> None:
        self.config = config or RoleConfig()
        self.dry_run = dry_run
        self._client: Any | None = None

    def generate(self, system: str, user: str) -> Generation:
        if self.dry_run:
            return self._dry_generate(system, user)
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_output_tokens": self.config.max_output_tokens,
        }
        if self.config.reasoning_effort != "none":
            kwargs["reasoning"] = {"effort": self.config.reasoning_effort}
        started = time.perf_counter()
        response = self._client.responses.create(**kwargs)
        latency_s = time.perf_counter() - started
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return Generation(
            text=extract_response_text(response),
            latency_s=latency_s,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_luna_cost(input_tokens, output_tokens),
            model=self.config.model,
            status=str(getattr(response, "status", "") or ""),
            incomplete_reason=str(
                getattr(getattr(response, "incomplete_details", None), "reason", "") or ""
            ),
        )

    def _dry_generate(self, system: str, user: str) -> Generation:
        del user
        text = "Identify the governing equation, then check the relevant constraints."
        if "critic" in system.lower():
            text = "rating: 4\nfailure: missing-constraint\nrepair: Check the boundary condition before finalizing."
        return Generation(
            text=text,
            latency_s=0.0,
            input_tokens=60,
            output_tokens=len(text.split()),
            cost_usd=estimate_luna_cost(60, len(text.split())),
            model=f"{self.config.model}:dry-run",
            status="completed",
        )


def plan_system_prompt() -> str:
    return (
        "Produce a concise explicit draft plan for solving the math problem. Do not state, "
        "calculate, quote, encode, or imply the final answer. Keep the plan below 60 tokens."
    )


def critic_system_prompt() -> str:
    return (
        "You are an answer-aware plan critic. Privately use the trusted reference answer "
        "to check the draft plan. Never state, calculate, quote, encode, or imply the final "
        "answer. Return exactly three lines: `rating: <1-5>`, `failure: <none|missing-constraint|"
        "incorrect-setup|invalid-inference|missing-case|other>`, and `repair: <optional concise "
        "non-answer instruction, 30 tokens or fewer>`."
    )


def build_critic_input(problem: Problem, plan: str) -> str:
    return (
        f"Problem:\n{problem.problem}\n\n"
        f"Trusted reference answer (private checking only):\n{problem.answer}\n\n"
        f"Draft plan:\n{plan}\n\n"
        "Return only a concise plan critique/update, with no final answer."
    )


def build_executor_instruction(plan: str, evaluation: CriticEvaluation) -> str:
    return (
        f"Draft plan:\n{plan}\n\n"
        f"Plan rating: {evaluation.rating}/5\n"
        f"Failure category: {evaluation.failure_category}\n"
        f"Repair instruction: {evaluation.repair or '(none)'}"
    )


def check_no_answer_leak(generation: Generation, expected_answer: str, max_words: int) -> TextCheck:
    text = generation.text.strip()
    if generation.status and generation.status != "completed":
        return TextCheck(False, f"incomplete response: {generation.incomplete_reason or generation.status}", "[REDACTED: incomplete]")
    if not text:
        return TextCheck(False, "empty response", "[REDACTED: empty]")
    if len(text.split()) > max_words:
        return TextCheck(False, f"over {max_words}-word cap", "[REDACTED: over budget]")
    lowered = text.lower()
    forbidden = ("\\boxed", "final answer", "the answer is", "answer:", "solution:")
    if any(fragment in lowered for fragment in forbidden):
        return TextCheck(False, "answer-revealing language", "[REDACTED: answer leak]")
    expected = normalize_answer(expected_answer).lower()
    if expected and expected in normalize_answer(text).lower():
        return TextCheck(False, "contains reference answer", "[REDACTED: answer leak]")
    return TextCheck(True, "passed", text)


def parse_critic_evaluation(generation: Generation, expected_answer: str) -> CriticEvaluation:
    leak_check = check_no_answer_leak(generation, expected_answer, max_words=70)
    if not leak_check.accepted:
        return CriticEvaluation(False, leak_check.reason, None, None, "")
    fields: dict[str, str] = {}
    for line in generation.text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    rating_text = fields.get("rating", "")
    category = fields.get("failure", "")
    repair = fields.get("repair", "")
    if not re.fullmatch(r"[1-5]", rating_text):
        return CriticEvaluation(False, "invalid or missing 1-5 rating", None, None, "")
    allowed_categories = {
        "none",
        "missing-constraint",
        "incorrect-setup",
        "invalid-inference",
        "missing-case",
        "other",
    }
    if category not in allowed_categories:
        return CriticEvaluation(False, "invalid or missing failure category", int(rating_text), None, "")
    if len(repair.split()) > 30:
        return CriticEvaluation(False, "repair exceeds 30-word cap", int(rating_text), category, "")
    return CriticEvaluation(True, "passed", int(rating_text), category, repair)


def run_critic_oracle(
    problems: list[Problem],
    answerer: LunaBackend,
    roles: RoleProtocol,
    output_dir: Path,
) -> dict[str, object]:
    """Run direct Luna vs answer-aware plan/critic/executor on the same items."""

    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    started = time.perf_counter()
    for problem in problems:
        arm_a = evaluate_one(problem, answerer, instruction=None, mode="direct-think")
        plan = roles.generate(plan_system_prompt(), f"Problem:\n{problem.problem}")
        plan_check = check_no_answer_leak(plan, problem.answer, max_words=60)
        critic = None
        critic_check = TextCheck(False, "not called", "[REDACTED: not called]")
        critic_evaluation = CriticEvaluation(False, "not called", None, None, "")
        executor = None
        if plan_check.accepted:
            critic = roles.generate(critic_system_prompt(), build_critic_input(problem, plan.text))
            critic_check = check_no_answer_leak(critic, problem.answer, max_words=70)
            critic_evaluation = parse_critic_evaluation(critic, problem.answer)
        if plan_check.accepted and critic_evaluation.accepted:
            executor = evaluate_one(
                problem,
                answerer,
                instruction=build_executor_instruction(plan.text, critic_evaluation),
                mode="oracle-critic-executor",
            )
        rows.append(
            experiment_row(
                problem, arm_a, plan, plan_check, critic, critic_check, critic_evaluation, executor
            )
        )

    paths = {
        "comparison": output_dir / "comparison.jsonl",
        "traces": output_dir / "critic_oracle_traces.txt",
        "metrics": output_dir / "metrics.json",
    }
    write_jsonl(paths["comparison"], rows)
    write_trace_report(paths["traces"], rows)
    metrics = summarize(rows)
    metrics["wall_time_s"] = round(time.perf_counter() - started, 6)
    metrics["paths"] = {name: str(path) for name, path in paths.items()}
    paths["metrics"].write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def experiment_row(
    problem: Problem,
    arm_a,
    plan: Generation,
    plan_check: TextCheck,
    critic: Generation | None,
    critic_check: TextCheck,
    critic_evaluation: CriticEvaluation,
    executor,
) -> dict[str, object]:
    return {
        "format": "answer_aware_critic_oracle_v1",
        "problem_id": problem.id,
        "problem": problem.problem,
        "reference_answer": problem.answer,
        "arm_a": arm_a.to_json(),
        "arm_b": {
            "oracle_label": "answer-aware oracle upper bound; not deployment-valid",
            "plan": generation_json(plan),
            "plan_check": text_check_json(plan_check),
            "critic": generation_json(critic) if critic else None,
            "critic_check": text_check_json(critic_check),
            "critic_evaluation": critic_evaluation_json(critic_evaluation),
            "executor": executor.to_json() if executor else None,
            "executor_score": executor.score if executor else 0.0,
        },
    }


def generation_json(generation: Generation) -> dict[str, object]:
    return {
        "text": generation.text,
        "model": generation.model,
        "status": generation.status,
        "incomplete_reason": generation.incomplete_reason,
        "latency_s": generation.latency_s,
        "input_tokens": generation.input_tokens,
        "output_tokens": generation.output_tokens,
        "cost_usd": generation.cost_usd,
    }


def text_check_json(check: TextCheck) -> dict[str, object]:
    return {"accepted": check.accepted, "reason": check.reason, "display_text": check.display_text}


def critic_evaluation_json(evaluation: CriticEvaluation) -> dict[str, object]:
    return {
        "accepted": evaluation.accepted,
        "reason": evaluation.reason,
        "rating": evaluation.rating,
        "failure_category": evaluation.failure_category,
        "repair": evaluation.repair,
    }


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    direct_scores = [float(row["arm_a"]["score"]) for row in rows]
    oracle_scores = [float(row["arm_b"]["executor_score"]) for row in rows]
    paired = {
        "oracle_only_wins": sum(a == 0 and b == 1 for a, b in zip(direct_scores, oracle_scores)),
        "direct_only_wins": sum(a == 1 and b == 0 for a, b in zip(direct_scores, oracle_scores)),
        "both_correct": sum(a == 1 and b == 1 for a, b in zip(direct_scores, oracle_scores)),
        "both_wrong_or_blocked": sum(a == 0 and b == 0 for a, b in zip(direct_scores, oracle_scores)),
    }
    plan_cost = sum(float(row["arm_b"]["plan"]["cost_usd"]) for row in rows)
    critic_cost = sum(
        float(row["arm_b"]["critic"]["cost_usd"])
        for row in rows
        if row["arm_b"]["critic"] is not None
    )
    executor_cost = sum(
        float(row["arm_b"]["executor"]["cost_usd"])
        for row in rows
        if row["arm_b"]["executor"] is not None
    )
    return {
        "num_problems": len(rows),
        "arm_a_direct_think_correct": int(sum(direct_scores)),
        "arm_b_oracle_critic_correct": int(sum(oracle_scores)),
        "arm_b_plan_leak_blocks": sum(not row["arm_b"]["plan_check"]["accepted"] for row in rows),
        "arm_b_critic_leak_or_format_blocks": sum(
            not row["arm_b"]["critic_evaluation"]["accepted"] for row in rows
        ),
        "paired": paired,
        "arm_a_cost_usd": sum(float(row["arm_a"]["cost_usd"]) for row in rows),
        "arm_b_plan_cost_usd": plan_cost,
        "arm_b_critic_cost_usd": critic_cost,
        "arm_b_executor_cost_usd": executor_cost,
        "arm_b_total_cost_usd": plan_cost + critic_cost + executor_cost,
    }


def write_trace_report(path: Path, rows: list[dict[str, object]]) -> None:
    sections = []
    for row in rows:
        arm_a = row["arm_a"]
        arm_b = row["arm_b"]
        executor = arm_b["executor"]
        lines = [
            "=" * 88,
            f"Problem: {row['problem_id']}",
            row["problem"],
            f"Reference answer: {row['reference_answer']}",
            "",
            "Arm A: direct Luna think mode",
            f"  answer: {arm_a['extracted_answer'] or '(empty)'}",
            f"  correct: {float(arm_a['score']):.0f}",
            f"  latency/cost: {float(arm_a['latency_s']):.2f}s / ${float(arm_a['cost_usd']):.6f}",
            "",
            "Arm B: answer-aware oracle plan/critic/executor",
            f"  plan: {arm_b['plan_check']['display_text']}",
            f"  plan leak check: {arm_b['plan_check']['reason']}",
            f"  critic update: {arm_b['critic_check']['display_text']}",
            f"  critic leak check: {arm_b['critic_check']['reason']}",
            f"  critic rating: {arm_b['critic_evaluation']['rating']}",
            f"  critic failure category: {arm_b['critic_evaluation']['failure_category']}",
            f"  critic repair: {arm_b['critic_evaluation']['repair'] or '(none)'}",
        ]
        if executor is None:
            lines.append("  executor: blocked before call")
        else:
            lines.extend(
                [
                    f"  final answer: {executor['extracted_answer'] or '(empty)'}",
                    f"  correct: {float(executor['score']):.0f}",
                    f"  latency/cost: {float(executor['latency_s']):.2f}s / ${float(executor['cost_usd']):.6f}",
                ]
            )
        sections.append("\n".join(lines))
    path.write_text("\n\n".join(sections) + ("\n" if sections else ""), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--problem-ids", help="Comma-separated exact dataset IDs.")
    parser.add_argument("--dataset-path", type=Path)
    parser.add_argument("--dataset-url", default=OMNI_MATH_RULE_URL)
    parser.add_argument("--min-difficulty", type=float)
    parser.add_argument("--max-difficulty", type=float)
    parser.add_argument("--output-dir", type=Path, default=Path("runs/critic_oracle"))
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--think-mode", choices=THINK_MODE_CHOICES, default="low")
    parser.add_argument("--answerer-max-output-tokens", type=int, default=1024)
    parser.add_argument("--role-max-output-tokens", type=int, default=512)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    problems = load_omni_math_rule(
        dataset_path=args.dataset_path,
        dataset_url=args.dataset_url,
        limit=None if args.problem_ids else args.limit,
        min_difficulty=args.min_difficulty,
        max_difficulty=args.max_difficulty,
    )
    if args.problem_ids:
        requested = [item.strip() for item in args.problem_ids.split(",") if item.strip()]
        by_id = {problem.id: problem for problem in problems}
        missing = [item for item in requested if item not in by_id]
        if missing:
            raise ValueError(f"requested dataset IDs not found: {', '.join(missing)}")
        problems = [by_id[item] for item in requested]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir / run_id
    effort = resolve_reasoning_effort("none", args.think_mode)
    answerer = LunaBackend(
        LunaConfig(model=args.model, reasoning_effort=effort, max_output_tokens=args.answerer_max_output_tokens),
        dry_run=args.dry_run,
    )
    roles = LunaRoleClient(
        RoleConfig(model=args.model, reasoning_effort=effort, max_output_tokens=args.role_max_output_tokens),
        dry_run=args.dry_run,
    )
    metrics = run_critic_oracle(problems, answerer, roles, output_dir)
    config_path = output_dir / "run_config.json"
    config_path.write_text(json.dumps(vars(args), default=str, indent=2), encoding="utf-8")
    metrics["paths"]["run_config"] = str(config_path)
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Wrote critic-oracle artifacts to {output_dir}")
    print(metrics)


if __name__ == "__main__":
    main()
