"""Budgeted note store for AdaptGym v0."""

from __future__ import annotations

from dataclasses import dataclass

from adaptgym.types import Action, ActionType


def count_tokens(text: str) -> int:
    """Count simple word tokens for deterministic note budgeting."""

    return len(text.split())


@dataclass
class NoteEntry:
    key: str
    content: str

    @property
    def tokens(self) -> int:
        return count_tokens(self.content)


class NoteStore:
    """A tiny persistent note store with a hard token budget."""

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self._entries: dict[str, NoteEntry] = {}
        self.budget_violations = 0

    @property
    def notes(self) -> dict[str, str]:
        return {key: entry.content for key, entry in self._entries.items()}

    @property
    def token_count(self) -> int:
        return sum(entry.tokens for entry in self._entries.values())

    def apply(self, action: Action) -> None:
        if action.type is ActionType.DO_NOTHING:
            return
        if action.type is ActionType.DELETE:
            if action.key is not None:
                self._entries.pop(action.key, None)
            return
        if action.key is None or action.content is None:
            raise ValueError(f"{action.type.value} requires key and content")

        before = dict(self._entries)
        self._entries[action.key] = NoteEntry(action.key, action.content)
        if self.token_count > self.budget:
            self._entries = before
            self.budget_violations += 1

    def answer_slot(self, slot: str) -> str | None:
        content = self._entries.get(slot)
        if content is None:
            return None
        marker = "prefers "
        if marker not in content.content:
            return None
        return content.content.split(marker, 1)[1].strip().rstrip(".")
