"""Public data types for AdaptGym v0."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    WRITE_MEMORY = "WRITE_MEMORY"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    DO_NOTHING = "DO_NOTHING"


@dataclass(frozen=True)
class Action:
    """A persistent action taken after an observation."""

    type: ActionType
    key: str | None = None
    content: str | None = None

    @classmethod
    def write_memory(cls, key: str, content: str) -> "Action":
        return cls(ActionType.WRITE_MEMORY, key=key, content=content)

    @classmethod
    def update(cls, key: str, content: str) -> "Action":
        return cls(ActionType.UPDATE, key=key, content=content)

    @classmethod
    def delete(cls, key: str) -> "Action":
        return cls(ActionType.DELETE, key=key)

    @classmethod
    def do_nothing(cls) -> "Action":
        return cls(ActionType.DO_NOTHING)


@dataclass(frozen=True)
class Observation:
    """One emitted session message."""

    session_index: int
    text: str
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Question:
    """Held-out multiple-choice question."""

    slot: str
    prompt: str
    choices: tuple[str, ...]
    answer: str


@dataclass(frozen=True)
class Episode:
    """A complete one-user stream plus held-out questions."""

    user_id: str
    observations: tuple[Observation, ...]
    questions: tuple[Question, ...]
    initial_profile: dict[str, str]
    final_profile: dict[str, str]
    config: Any


@dataclass(frozen=True)
class Score:
    """Deterministic score for an episode run."""

    accuracy: float
    correct: int
    total: int
    efficiency: float
    note_tokens: int
    note_budget: int
    budget_violations: int
    memory_precision: float
    memory_recall: float
    downstream_score: float


@dataclass(frozen=True)
class EvaluationResult:
    """Trace and final score for one policy."""

    policy_name: str
    score: Score
    actions: tuple[Action, ...]
    answers: tuple[str, ...]
    notes: dict[str, str]
