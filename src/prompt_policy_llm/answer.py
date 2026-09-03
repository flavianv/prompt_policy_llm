"""Answer extraction and lightweight rule-based scoring."""

from __future__ import annotations

import re


_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def extract_boxed_answer(text: str) -> str | None:
    """Return the last LaTeX boxed answer in a model response."""

    matches: list[str] = []
    cursor = 0
    marker = "\\boxed{"
    while True:
        start = text.find(marker, cursor)
        if start == -1:
            break
        content_start = start + len(marker)
        depth = 1
        index = content_start
        while index < len(text) and depth > 0:
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        if depth == 0:
            matches.append(text[content_start : index - 1].strip())
        cursor = content_start
    if not matches:
        return None
    return matches[-1].strip()


def extract_final_answer(text: str) -> str:
    """Extract a final answer from text using boxed answers first."""

    boxed = extract_boxed_answer(text)
    if boxed is not None:
        return boxed

    numbers = _NUMBER_RE.findall(text)
    if numbers:
        return numbers[-1]
    return text.strip()


def normalize_answer(answer: str) -> str:
    """Normalize simple exact answers for Omni-MATH rule matching."""

    normalized = answer.strip()
    normalized = normalized.replace("$", "")
    normalized = normalized.replace("\\,", "")
    normalized = normalized.replace("\\left", "")
    normalized = normalized.replace("\\right", "")
    normalized = normalized.replace("\\dfrac", "\\frac")
    normalized = normalized.replace("\\tfrac", "\\frac")
    normalized = normalized.replace(",", "")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*([{}^_()+\\/=*-])\s*", r"\1", normalized)
    return normalized


def exact_match_score(prediction: str, expected: str) -> float:
    """Score exact answer equality after conservative normalization."""

    return float(normalize_answer(prediction) == normalize_answer(expected))
