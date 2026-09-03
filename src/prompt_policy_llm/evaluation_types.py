"""Small helpers separated to avoid circular imports in training-format builders."""

from __future__ import annotations

from .schema import EvalItem


def group_by_problem(items: list[EvalItem]) -> dict[str, list[EvalItem]]:
    grouped: dict[str, list[EvalItem]] = {}
    for item in items:
        grouped.setdefault(item.problem.id, []).append(item)
    return grouped

