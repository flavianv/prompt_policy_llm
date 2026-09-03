"""Human-readable paired baseline/controller trace reports."""

from __future__ import annotations

import argparse
import json
import textwrap
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .schema import EvalItem


def write_trace_report(path: Path, items: list[EvalItem]) -> None:
    """Write one complete, readable trace for every evaluated problem."""

    rows = []
    for item in items:
        row = item.to_json()
        row["problem_text"] = item.problem.problem
        rows.append(row)
    path.write_text(format_trace_rows(rows), encoding="utf-8")


def format_trace_rows(rows: list[dict[str, Any]]) -> str:
    """Render evaluation rows grouped by problem, preserving raw solver output."""

    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in rows:
        grouped.setdefault(str(row["problem_id"]), []).append(row)

    sections = []
    for index, (problem_id, problem_rows) in enumerate(grouped.items(), start=1):
        first = problem_rows[0]
        baseline = next((row for row in problem_rows if row["mode"] == "baseline"), None)
        controlled = [row for row in problem_rows if row["mode"] == "controlled"]
        lines = [
            "=" * 88,
            f"Trace {index}: {problem_id}",
            f"Source: {first.get('source') or 'unknown'}",
            f"Domain: {first.get('domain') or 'unknown'}",
            f"Difficulty: {first.get('difficulty') if first.get('difficulty') is not None else 'unknown'}",
            "",
            "Problem:",
            first.get("problem_text") or "(problem text unavailable in this artifact)",
            "",
            f"Reference answer: {first.get('expected_answer', '')}",
        ]
        if baseline is not None:
            lines.extend(format_condition("Baseline (no controller)", baseline))
        for sample_index, controlled_row in enumerate(controlled, start=1):
            title = "Controlled policy" if len(controlled) == 1 else f"Controlled policy sample {sample_index}"
            lines.extend(format_condition(title, controlled_row))
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + ("\n" if sections else "")


def format_condition(title: str, row: dict[str, Any]) -> list[str]:
    instruction = row.get("instruction") or "(none)"
    response = row.get("response") or "(empty)"
    lines = [
        "",
        f"--- {title} ---",
        f"Policy hint: {instruction}",
        "Raw solver output:",
        indent(response),
        f"Final answer extracted: {row.get('extracted_answer') or '(empty)'}",
        f"Exact-match score: {float(row.get('score', 0)):.0f}",
        f"Solver status: {row.get('generation_status') or 'unknown'}",
    ]
    if row.get("incomplete_reason"):
        lines.append(f"Incomplete reason: {row['incomplete_reason']}")
    lines.extend(
        [
            f"Latency: {float(row.get('latency_s', 0)):.2f}s",
            f"Estimated Luna cost: ${float(row.get('cost_usd', 0)):.6f}",
        ]
    )
    if row.get("controller_token_budget"):
        lines.append(
            "Controller tokens: "
            f"{row.get('controller_output_tokens', 0)}/{row['controller_token_budget']}"
        )
    return lines


def indent(text: str) -> str:
    return textwrap.indent(text, "  ")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def add_problem_text_from_rollouts(
    prediction_rows: list[dict[str, Any]],
    rollout_rows: list[dict[str, Any]],
) -> None:
    """Rehydrate problem text for runs created before trace reports existed."""

    problem_text_by_id: dict[str, str] = {}
    for rollout in rollout_rows:
        messages = rollout.get("messages", [])
        user_message = next(
            (message.get("content", "") for message in messages if message.get("role") == "user"),
            "",
        )
        marker = "problem:\n"
        if marker in user_message:
            problem_text_by_id[str(rollout["group_id"])] = user_message.split(marker, 1)[1]
    for row in prediction_rows:
        row.setdefault("problem_text", problem_text_by_id.get(str(row["problem_id"]), ""))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--rollouts", type=Path, help="Needed only for legacy prediction files without problem text.")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(args.predictions)
    if args.rollouts:
        add_problem_text_from_rollouts(rows, read_jsonl(args.rollouts))
    args.output.write_text(format_trace_rows(rows), encoding="utf-8")
    print(f"Wrote trace report to {args.output}")


if __name__ == "__main__":
    main()
