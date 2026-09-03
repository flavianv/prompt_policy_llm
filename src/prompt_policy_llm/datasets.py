"""Dataset loading for Omni-MATH rule experiments."""

from __future__ import annotations

import json
import random
import urllib.request
from collections.abc import Iterable
from pathlib import Path

from .schema import Problem


OMNI_MATH_RULE_URL = (
    "https://raw.githubusercontent.com/KbsdJames/omni-math-rule/main/"
    "omni_math_rule.jsonl"
)


def load_omni_math_rule(
    dataset_path: Path | None = None,
    dataset_url: str = OMNI_MATH_RULE_URL,
    limit: int | None = None,
    seed: int = 0,
    shuffle: bool = False,
    min_difficulty: float | None = None,
    max_difficulty: float | None = None,
) -> list[Problem]:
    """Load the rule-verifiable Omni-MATH JSONL subset."""

    rows = _read_jsonl_path(dataset_path) if dataset_path else _read_jsonl_url(dataset_url)
    problems = [problem_from_row(index, row) for index, row in enumerate(rows)]
    problems = filter_by_difficulty(problems, min_difficulty, max_difficulty)
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(problems)
    if limit is not None:
        problems = problems[:limit]
    return problems


def filter_by_difficulty(
    problems: list[Problem],
    min_difficulty: float | None,
    max_difficulty: float | None,
) -> list[Problem]:
    filtered = problems
    if min_difficulty is not None:
        filtered = [
            problem
            for problem in filtered
            if problem.difficulty is not None and problem.difficulty >= min_difficulty
        ]
    if max_difficulty is not None:
        filtered = [
            problem
            for problem in filtered
            if problem.difficulty is not None and problem.difficulty <= max_difficulty
        ]
    return filtered


def problem_from_row(index: int, row: dict[str, object]) -> Problem:
    if row.get("id"):
        problem_id = str(row["id"])
    elif row.get("source"):
        problem_id = f"{row['source']}:{index}"
    else:
        problem_id = str(index)
    problem = str(row["problem"])
    answer = str(row["answer"])
    domain = row.get("domain")
    if isinstance(domain, list):
        domain_text = " | ".join(str(item) for item in domain)
    else:
        domain_text = str(domain or "")
    difficulty = row.get("difficulty")
    difficulty_value = float(difficulty) if difficulty is not None else None
    return Problem(
        id=problem_id,
        problem=problem,
        answer=answer,
        domain=domain_text,
        difficulty=difficulty_value,
        source=str(row.get("source") or ""),
    )


def _read_jsonl_path(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return []
    with path.open("r", encoding="utf-8") as handle:
        return list(_parse_jsonl(handle))


def _read_jsonl_url(url: str) -> list[dict[str, object]]:
    with urllib.request.urlopen(url, timeout=60) as response:
        lines = (line.decode("utf-8") for line in response)
        return list(_parse_jsonl(lines))


def _parse_jsonl(lines: Iterable[str]) -> Iterable[dict[str, object]]:
    for line in lines:
        stripped = line.strip()
        if stripped:
            yield json.loads(stripped)
