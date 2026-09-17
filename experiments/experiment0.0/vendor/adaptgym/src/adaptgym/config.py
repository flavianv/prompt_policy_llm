"""Configuration for AdaptGym v0."""

from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_DISTRACTOR_TYPES = (
    "generic_chatter",
    "unrelated_attribute",
    "repeat_known",
    "stale_fact",
    "other_person_preference",
    "product_description",
    "near_miss_lure",
)


@dataclass(frozen=True)
class DifficultyConfig:
    """Difficulty knobs for one deterministic AdaptGym v0 episode."""

    profile_size: int = 5
    session_count: int = 8
    distractors_per_session: int = 2
    distractor_types: tuple[str, ...] = field(default_factory=lambda: DEFAULT_DISTRACTOR_TYPES)
    lexical_similarity: float = 0.5
    update_rate: float = 0.35
    delayed_query_horizon: int = 2
    note_budget: int = 120
    choices_per_question: int = 4
    seed: int = 0

    def validate(self) -> None:
        if self.profile_size < 1:
            raise ValueError("profile_size must be at least 1")
        if self.session_count < 1:
            raise ValueError("session_count must be at least 1")
        if self.distractors_per_session < 0:
            raise ValueError("distractors_per_session must be non-negative")
        if not 0.0 <= self.lexical_similarity <= 1.0:
            raise ValueError("lexical_similarity must be between 0 and 1")
        if not 0.0 <= self.update_rate <= 1.0:
            raise ValueError("update_rate must be between 0 and 1")
        if self.delayed_query_horizon < 0:
            raise ValueError("delayed_query_horizon must be non-negative")
        if self.note_budget < 1:
            raise ValueError("note_budget must be at least 1")
        if self.choices_per_question < 2:
            raise ValueError("choices_per_question must be at least 2")
        unknown = sorted(set(self.distractor_types) - set(DEFAULT_DISTRACTOR_TYPES))
        if unknown:
            raise ValueError(f"unknown distractor type(s): {', '.join(unknown)}")
