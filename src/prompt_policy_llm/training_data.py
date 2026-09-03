"""Training-data loading and rendering for the controller."""

from __future__ import annotations

import json
from pathlib import Path


def load_chat_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            validate_chat_row(row, line_number)
            rows.append(row)
    if not rows:
        raise ValueError(f"no training rows found in {path}")
    return rows


def validate_chat_row(row: dict[str, object], line_number: int) -> None:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) < 3:
        raise ValueError(f"line {line_number}: expected at least three chat messages")

    roles = [message.get("role") for message in messages if isinstance(message, dict)]
    if roles[:2] != ["system", "user"] or roles[-1] != "assistant":
        raise ValueError(f"line {line_number}: expected system, user, assistant chat format")

    action = messages[-1].get("content") if isinstance(messages[-1], dict) else None
    if not isinstance(action, str) or not action.strip():
        raise ValueError(f"line {line_number}: assistant instruction is empty")


def split_prompt_and_completion(row: dict[str, object]) -> tuple[str, str]:
    messages = row["messages"]
    assert isinstance(messages, list)
    prompt_messages = messages[:-1]
    assistant = messages[-1]
    assert isinstance(assistant, dict)
    prompt = render_messages(prompt_messages)
    completion = str(assistant["content"]).strip()
    return prompt, completion


def render_messages(messages: list[object]) -> str:
    rendered: list[str] = []
    for message in messages:
        assert isinstance(message, dict)
        role = str(message["role"]).strip()
        content = str(message["content"]).strip()
        rendered.append(f"<|{role}|>\n{content}")
    rendered.append("<|assistant|>\n")
    return "\n".join(rendered)

