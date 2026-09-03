"""Compare frozen-solver answers with and without a tiny prompt policy."""

from __future__ import annotations

import argparse
import textwrap
import time

from .backend import THINK_MODE_CHOICES, LunaBackend, LunaConfig, resolve_reasoning_effort
from .controller import ControllerModelConfig, SMALLEST_CONTROLLER_MODEL, TinyController
from .evaluation import build_controller_state, evaluate_one, get_controller_action
from .schema import EvalItem, Problem


def compare_problem(
    problem: Problem,
    backend: LunaBackend,
    controller: TinyController,
) -> tuple[EvalItem, EvalItem]:
    """Run the frozen solver once without and once with a controller action."""

    baseline = evaluate_one(problem, backend, instruction=None, mode="baseline")
    started = time.perf_counter()
    action = get_controller_action(controller, build_controller_state(problem), sample_index=0)
    controller_latency_s = time.perf_counter() - started
    controlled = evaluate_one(
        problem,
        backend,
        instruction=action.instruction,
        mode="controlled",
        controller_latency_s=controller_latency_s,
        controller_action=action,
    )
    return baseline, controlled


def format_comparison(problem: Problem, baseline: EvalItem, controlled: EvalItem) -> str:
    """Render the paired result as a compact, readable two-column report."""

    rows = [
        ("Controller instruction", "(none)", controlled.instruction or "(empty)"),
        ("Model output", baseline.response, controlled.response),
        ("Extracted answer", baseline.extracted_answer, controlled.extracted_answer),
        ("Reference answer", problem.answer, problem.answer),
        ("Exact-match score", f"{baseline.score:.0f}", f"{controlled.score:.0f}"),
        ("Solver status", baseline.generation_status or "unknown", controlled.generation_status or "unknown"),
        ("End-to-end latency", format_seconds(baseline.latency_s), format_seconds(controlled.latency_s)),
        ("Estimated Luna cost", format_cost(baseline.cost_usd), format_cost(controlled.cost_usd)),
    ]
    label_width = max(len(label) for label, _, _ in rows)
    value_width = 48
    lines = [
        "Problem:",
        problem.problem,
        "",
        f"{'':{label_width}}  {'Baseline (no policy)':<{value_width}}  Controlled (policy)",
        f"{'-' * label_width}  {'-' * value_width}  {'-' * value_width}",
    ]
    for label, baseline_value, controlled_value in rows:
        lines.extend(
            format_row(
                label,
                baseline_value,
                controlled_value,
                label_width=label_width,
                value_width=value_width,
            )
        )
    if controlled.controller_token_budget:
        lines.append(
            "Controller token budget: "
            f"{controlled.controller_output_tokens}/{controlled.controller_token_budget}"
        )
    return "\n".join(lines)


def format_row(
    label: str,
    baseline_value: str,
    controlled_value: str,
    *,
    label_width: int,
    value_width: int,
) -> list[str]:
    baseline_lines = wrap_value(baseline_value, value_width)
    controlled_lines = wrap_value(controlled_value, value_width)
    height = max(len(baseline_lines), len(controlled_lines))
    lines = []
    for index in range(height):
        row_label = label if index == 0 else ""
        left = baseline_lines[index] if index < len(baseline_lines) else ""
        right = controlled_lines[index] if index < len(controlled_lines) else ""
        lines.append(f"{row_label:<{label_width}}  {left:<{value_width}}  {right}")
    return lines


def wrap_value(value: str, width: int) -> list[str]:
    lines = textwrap.wrap(
        str(value).replace("\n", " "),
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return lines or ["(empty)"]


def format_seconds(value: float) -> str:
    return f"{value:.2f}s"


def format_cost(value: float) -> str:
    return f"${value:.6f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem", required=True, help="Problem text sent to the frozen solver.")
    parser.add_argument("--answer", required=True, help="Reference answer used for exact-match scoring.")
    parser.add_argument("--problem-id", default="ad-hoc")
    parser.add_argument("--domain", default="ad-hoc")
    parser.add_argument("--difficulty", type=float)
    parser.add_argument("--luna-model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", default="none")
    parser.add_argument(
        "--think-mode",
        choices=THINK_MODE_CHOICES,
        help="Native Luna reasoning effort. Overrides --reasoning-effort when supplied.",
    )
    parser.add_argument(
        "--show-work",
        action="store_true",
        help="Ask Luna for a concise derivation before the boxed final answer.",
    )
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--controller-model", default=SMALLEST_CONTROLLER_MODEL)
    parser.add_argument("--controller-tokens", type=int, default=30)
    parser.add_argument("--controller-temperature", type=float, default=0.7)
    parser.add_argument("--controller-top-p", type=float, default=0.9)
    parser.add_argument("--controller-device", default="auto")
    parser.add_argument("--dry-run", action="store_true", help="Exercise the comparison without API or model calls.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    problem = Problem(
        id=args.problem_id,
        problem=args.problem,
        answer=args.answer,
        domain=args.domain,
        difficulty=args.difficulty,
    )
    backend = LunaBackend(
        LunaConfig(
            model=args.luna_model,
            reasoning_effort=resolve_reasoning_effort(args.reasoning_effort, args.think_mode),
            max_output_tokens=args.max_output_tokens,
            show_work=args.show_work,
        ),
        dry_run=args.dry_run,
    )
    controller = TinyController(
        ControllerModelConfig(
            model=args.controller_model,
            max_new_tokens=args.controller_tokens,
            temperature=args.controller_temperature,
            top_p=args.controller_top_p,
            device=args.controller_device,
        ),
        dry_run=args.dry_run,
    )
    baseline, controlled = compare_problem(problem, backend, controller)
    print(format_comparison(problem, baseline, controlled))


if __name__ == "__main__":
    main()
