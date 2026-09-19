"""Baseline policies for AdaptGym v0."""

from __future__ import annotations

import re

from adaptgym.memory import NoteStore
from adaptgym.types import Action, Observation, Question


class NoPersistentNotesPolicy:
    name = "no-notes"

    def observe(self, observation: Observation, notes: NoteStore) -> Action:
        return Action.do_nothing()

    def answer(self, question: Question, notes: NoteStore) -> str:
        return question.choices[0]


class NaiveStoragePolicy:
    """Stores any first-person preference-looking text without using metadata."""

    name = "naive"

    def observe(self, observation: Observation, notes: NoteStore) -> Action:
        parsed = _parse_first_person_preference(observation.text)
        if parsed is None:
            return Action.do_nothing()
        slot, value, is_update = parsed
        content = f"user prefers {value}"
        if is_update or slot in notes.notes:
            return Action.update(slot, content)
        return Action.write_memory(slot, content)

    def answer(self, question: Question, notes: NoteStore) -> str:
        value = notes.answer_slot(question.slot)
        if value in question.choices:
            return value
        return question.choices[0]


class OraclePolicy:
    """Privileged upper-bound policy that can read episode annotations."""

    name = "oracle"

    def observe(self, observation: Observation, notes: NoteStore) -> Action:
        if not observation.metadata.get("is_profile_event"):
            return Action.do_nothing()
        slot = observation.metadata["slot"]
        value = observation.metadata["value"]
        content = f"user prefers {value}"
        if observation.kind == "true_update" or slot in notes.notes:
            return Action.update(slot, content)
        return Action.write_memory(slot, content)

    def answer(self, question: Question, notes: NoteStore) -> str:
        value = notes.answer_slot(question.slot)
        if value in question.choices:
            return value
        return question.choices[0]


POLICIES = {
    NoPersistentNotesPolicy.name: NoPersistentNotesPolicy,
    NaiveStoragePolicy.name: NaiveStoragePolicy,
    OraclePolicy.name: OraclePolicy,
}


def _parse_first_person_preference(text: str) -> tuple[str, str, bool] | None:
    update_match = re.search(r"I now prefer (?P<value>.+?) instead of .+?\.", text)
    if update_match:
        slot_match = re.search(r"about (?P<slot>[a-z_]+):", text)
        if slot_match:
            return slot_match.group("slot"), update_match.group("value"), True

    preference_match = re.search(r"For (?P<slot>[a-z_]+), I prefer (?P<value>.+?)\.", text)
    if preference_match:
        return preference_match.group("slot"), preference_match.group("value"), False

    return None
