"""Evaluation loop for baseline and controlled prompt policies."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Protocol

from .answer import exact_match_score, extract_final_answer
from .finetune import build_rollout_rows, build_sft_rows
from .schema import ControllerAction, EvalItem, Generation, Problem


class BackendProtocol(Protocol):
    def generate(self, problem: str, instruction: str | None = None) -> Generation:
        ...


class ControllerProtocol(Protocol):
    def instruct(self, state: str, sample_index: int = 0) -> str:
        ...


def evaluate_problems(
    problems: list[Problem],
    backend: BackendProtocol,
    controller: ControllerProtocol | None,
    output_dir: Path,
    mode: str = "both",
    controller_samples: int = 1,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = output_dir / "predictions.jsonl"
    rollouts_path = output_dir / "controller_rollouts.jsonl"
    sft_path = output_dir / "controller_sft_seed.jsonl"
    summary_path = output_dir / "metrics.json"

    eval_items: list[EvalItem] = []
    started = time.perf_counter()

    with predictions_path.open("w", encoding="utf-8") as pred_handle:
        for problem in problems:
            if mode in {"baseline", "both"}:
                baseline_item = evaluate_one(problem, backend, instruction=None, mode="baseline")
                eval_items.append(baseline_item)
                pred_handle.write(json.dumps(baseline_item.to_json(), ensure_ascii=False) + "\n")

            if mode in {"controlled", "both"}:
                if controller is None:
                    raise ValueError("controller is required for controlled evaluation")
                state = build_controller_state(problem)
                for sample_index in range(controller_samples):
                    controller_started = time.perf_counter()
                    action = get_controller_action(controller, state, sample_index)
                    controller_latency_s = time.perf_counter() - controller_started
                    controlled_item = evaluate_one(
                        problem,
                        backend,
                        instruction=action.instruction,
                        mode="controlled",
                        sample_index=sample_index,
                        controller_latency_s=controller_latency_s,
                        controller_action=action,
                    )
                    eval_items.append(controlled_item)
                    pred_handle.write(json.dumps(controlled_item.to_json(), ensure_ascii=False) + "\n")

    rollout_rows = build_rollout_rows(eval_items)
    sft_rows = build_sft_rows(eval_items)
    write_jsonl(rollouts_path, rollout_rows)
    write_jsonl(sft_path, sft_rows)

    summary = summarize(eval_items)
    summary["wall_time_s"] = round(time.perf_counter() - started, 6)
    summary["paths"] = {
        "predictions": str(predictions_path),
        "controller_rollouts": str(rollouts_path),
        "controller_sft_seed": str(sft_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def evaluate_one(
    problem: Problem,
    backend: BackendProtocol,
    instruction: str | None,
    mode: str,
    sample_index: int = 0,
    controller_latency_s: float = 0.0,
    controller_action: ControllerAction | None = None,
) -> EvalItem:
    generation = backend.generate(problem.problem, instruction=instruction)
    extracted = extract_final_answer(generation.text)
    score = exact_match_score(extracted, problem.answer)
    return EvalItem(
        problem=problem,
        mode=mode,
        instruction=instruction,
        response=generation.text,
        extracted_answer=extracted,
        score=score,
        latency_s=generation.latency_s + controller_latency_s,
        backend_latency_s=generation.latency_s,
        controller_latency_s=controller_latency_s,
        input_tokens=generation.input_tokens,
        output_tokens=generation.output_tokens,
        cost_usd=generation.cost_usd,
        model=generation.model,
        generation_status=generation.status,
        incomplete_reason=generation.incomplete_reason,
        controller_model=controller_action.model if controller_action else "",
        controller_output_tokens=controller_action.output_tokens if controller_action else 0,
        controller_token_budget=controller_action.token_budget if controller_action else 0,
        controller_over_budget=controller_action.over_budget if controller_action else False,
        sample_index=sample_index,
    )


def get_controller_action(
    controller: ControllerProtocol,
    state: str,
    sample_index: int,
) -> ControllerAction:
    act = getattr(controller, "act", None)
    if callable(act):
        return act(state, sample_index=sample_index)
    instruction = controller.instruct(state, sample_index=sample_index)
    return ControllerAction(
        instruction=instruction,
        output_tokens=len(instruction.split()),
        token_budget=30,
        model=controller.__class__.__name__,
        raw_text=instruction,
    )


def build_controller_state(problem: Problem) -> str:
    lines = [
        "benchmark: omni-math-rule",
        f"domain: {problem.domain or 'unknown'}",
        f"difficulty: {problem.difficulty if problem.difficulty is not None else 'unknown'}",
        "problem:",
        problem.problem,
    ]
    return "\n".join(lines)


def summarize(items: list[EvalItem]) -> dict[str, object]:
    by_mode: dict[str, list[EvalItem]] = {}
    for item in items:
        by_mode.setdefault(item.mode, []).append(item)

    summary: dict[str, object] = {"num_predictions": len(items), "modes": {}}
    modes = summary["modes"]
    assert isinstance(modes, dict)
    for mode, mode_items in sorted(by_mode.items()):
        latencies = [item.latency_s for item in mode_items]
        costs = [item.cost_usd for item in mode_items]
        scores = [item.score for item in mode_items]
        modes[mode] = {
            "n": len(mode_items),
            "accuracy": sum(scores) / len(scores) if scores else 0.0,
            "median_latency_s": statistics.median(latencies) if latencies else 0.0,
            "p95_latency_s": percentile(latencies, 95),
            "total_cost_usd": sum(costs),
            "mean_cost_usd": sum(costs) / len(costs) if costs else 0.0,
            "input_tokens": sum(item.input_tokens for item in mode_items),
            "output_tokens": sum(item.output_tokens for item in mode_items),
        }
        controller_items = [item for item in mode_items if item.controller_token_budget]
        if controller_items:
            modes[mode]["controller_output_tokens"] = sum(
                item.controller_output_tokens for item in controller_items
            )
            modes[mode]["mean_controller_output_tokens"] = (
                sum(item.controller_output_tokens for item in controller_items)
                / len(controller_items)
            )
            modes[mode]["controller_token_budget"] = max(
                item.controller_token_budget for item in controller_items
            )
            modes[mode]["controller_budget_violations"] = sum(
                item.controller_over_budget for item in controller_items
            )

    if "baseline" in modes and "controlled" in modes:
        baseline_accuracy = modes["baseline"]["accuracy"]
        controlled_accuracy = modes["controlled"]["accuracy"]
        summary["lift_over_baseline"] = controlled_accuracy - baseline_accuracy
    return summary


def percentile(values: list[float], q: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((q / 100) * (len(ordered) - 1))))
    return ordered[index]


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
