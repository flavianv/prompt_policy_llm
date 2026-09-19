"""Synthetic deterministic sequential note-taking environment."""

from __future__ import annotations

import random
from dataclasses import asdict
from typing import Protocol

from adaptgym.config import DifficultyConfig
from adaptgym.memory import NoteStore
from adaptgym.types import Action, Episode, EvaluationResult, Observation, Question, Score


class Policy(Protocol):
    name: str

    def observe(self, observation: Observation, notes: NoteStore) -> Action:
        ...

    def answer(self, question: Question, notes: NoteStore) -> str:
        ...


SLOT_VALUES: dict[str, tuple[str, ...]] = {
    "breakfast": ("oatmeal", "eggs", "yogurt", "toast", "smoothies"),
    "exercise": ("cycling", "yoga", "running", "rowing", "pilates"),
    "music": ("jazz", "ambient", "salsa", "classical", "synthwave"),
    "meeting_style": ("bullet agendas", "freeform discussion", "silent docs", "whiteboards", "demo-first meetings"),
    "travel_seat": ("aisle", "window", "front row", "extra legroom", "quiet car"),
    "reading": ("science fiction", "biographies", "mysteries", "history", "essays"),
    "drink": ("green tea", "espresso", "sparkling water", "black coffee", "mint tea"),
    "coding_music": ("silence", "lo-fi", "instrumental jazz", "rain sounds", "piano"),
    "notification_style": ("morning summary", "instant alerts", "weekly digest", "only urgent alerts", "end-of-day recap"),
    "workout_time": ("morning", "lunch break", "late afternoon", "evening", "weekend only"),
    "lunch": ("salads", "ramen", "grain bowls", "sandwiches", "tacos"),
    "learning_style": ("examples first", "theory first", "quizzes", "projects", "flashcards"),
}

OTHER_PEOPLE = ("Riley", "Morgan", "Sam", "Jordan")
GENERIC_CHATTER = (
    "The weather was surprisingly clear today.",
    "I had a busy morning and moved a few errands around.",
    "That reminds me to clean up my calendar later.",
    "I might take a short walk after work.",
)
UNRELATED_ATTRIBUTES = (
    "I like the blue label on that package, but it does not change what I prefer.",
    "The app's compact layout looks nice, but that is not a preference to remember.",
    "I noticed the quiet lobby music, but I am not choosing a music preference here.",
    "The sample itinerary has a short layover, but it is only an example.",
)
PRODUCT_DESCRIPTIONS = (
    "The catalog says the backpack has three compartments and a rain cover.",
    "The headphones product page mentions foam ear cups and USB-C charging.",
    "The blender description highlights a steel blade and dishwasher-safe jar.",
    "The chair listing describes adjustable arms and a breathable mesh back.",
)


class AdaptGymEnv:
    """Generate and score one-user AdaptGym v0 episodes."""

    def __init__(self, config: DifficultyConfig | None = None) -> None:
        self.config = config or DifficultyConfig()
        self.config.validate()

    def generate_episode(self) -> Episode:
        rng = random.Random(self.config.seed)
        slots = rng.sample(list(SLOT_VALUES), self.config.profile_size)
        initial_profile = {slot: rng.choice(SLOT_VALUES[slot]) for slot in slots}
        current_profile = dict(initial_profile)
        known_slots: set[str] = set()
        last_profile_session = {slot: -1 for slot in slots}
        observations: list[Observation] = []

        for session_index in range(self.config.session_count):
            true_observation = self._true_observation(
                rng=rng,
                session_index=session_index,
                slots=slots,
                current_profile=current_profile,
                known_slots=known_slots,
                last_profile_session=last_profile_session,
            )
            distractors = [
                self._distractor_observation(rng, session_index, slots, current_profile)
                for _ in range(self.config.distractors_per_session)
            ]
            session_items = [true_observation, *distractors]
            rng.shuffle(session_items)
            observations.extend(session_items)

        questions = self._questions(rng, slots, current_profile, last_profile_session)
        return Episode(
            user_id=f"user-{self.config.seed}",
            observations=tuple(observations),
            questions=tuple(questions),
            initial_profile=initial_profile,
            final_profile=current_profile,
            config=asdict(self.config),
        )

    def evaluate_policy(self, policy: Policy, episode: Episode | None = None) -> EvaluationResult:
        episode = episode or self.generate_episode()
        notes = NoteStore(episode.config["note_budget"])
        actions: list[Action] = []

        for observation in episode.observations:
            action = policy.observe(observation, notes)
            notes.apply(action)
            actions.append(action)

        answers = tuple(policy.answer(question, notes) for question in episode.questions)
        correct = sum(answer == question.answer for answer, question in zip(answers, episode.questions))
        total = len(episode.questions)
        accuracy = correct / total if total else 0.0
        memory_precision, memory_recall = self._memory_quality(notes.notes, episode.final_profile)
        efficiency = self._efficiency(notes.token_count, episode.config["note_budget"])
        downstream_score = accuracy * efficiency

        return EvaluationResult(
            policy_name=policy.name,
            score=Score(
                accuracy=accuracy,
                correct=correct,
                total=total,
                efficiency=efficiency,
                note_tokens=notes.token_count,
                note_budget=episode.config["note_budget"],
                budget_violations=notes.budget_violations,
                memory_precision=memory_precision,
                memory_recall=memory_recall,
                downstream_score=downstream_score,
            ),
            actions=tuple(actions),
            answers=answers,
            notes=notes.notes,
        )

    def _true_observation(
        self,
        rng: random.Random,
        session_index: int,
        slots: list[str],
        current_profile: dict[str, str],
        known_slots: set[str],
        last_profile_session: dict[str, int],
    ) -> Observation:
        unseen = [slot for slot in slots if slot not in known_slots]
        can_update = not unseen and bool(known_slots) and rng.random() < self.config.update_rate
        if can_update:
            slot = rng.choice(sorted(known_slots))
            old_value = current_profile[slot]
            new_value = self._different_value(rng, slot, old_value)
            current_profile[slot] = new_value
            last_profile_session[slot] = session_index
            return Observation(
                session_index=session_index,
                text=f"I changed my mind about {slot}: I now prefer {new_value} instead of {old_value}.",
                kind="true_update",
                metadata={"slot": slot, "value": new_value, "old_value": old_value, "is_profile_event": True},
            )

        slot = rng.choice(unseen or slots)
        value = current_profile[slot]
        known_slots.add(slot)
        last_profile_session[slot] = session_index
        return Observation(
            session_index=session_index,
            text=f"For {slot}, I prefer {value}.",
            kind="true_preference",
            metadata={"slot": slot, "value": value, "is_profile_event": True},
        )

    def _distractor_observation(
        self,
        rng: random.Random,
        session_index: int,
        slots: list[str],
        current_profile: dict[str, str],
    ) -> Observation:
        kind = rng.choice(self.config.distractor_types)
        if kind == "repeat_known":
            slot = rng.choice(slots)
            value = current_profile[slot]
            text = f"As background only, I previously said I still prefer {value} for {slot}."
        elif kind == "stale_fact":
            slot = rng.choice(slots)
            stale_value = self._different_value(rng, slot, current_profile[slot])
            text = f"Historical note, not current: I used to prefer {stale_value} for {slot}."
        elif kind == "other_person_preference":
            person = rng.choice(OTHER_PEOPLE)
            slot = rng.choice(slots)
            value = rng.choice(SLOT_VALUES[slot])
            text = f"{person} is different from me: {person} prefers {value} for {slot}."
        elif kind == "unrelated_attribute":
            text = rng.choice(UNRELATED_ATTRIBUTES)
        elif kind == "product_description":
            if rng.random() < self.config.lexical_similarity:
                slot = rng.choice(slots)
                value = rng.choice(SLOT_VALUES[slot])
                text = f"The product description mentions {value} for {slot}, but I am only reading specs."
            else:
                text = rng.choice(PRODUCT_DESCRIPTIONS)
        elif kind == "near_miss_lure":
            slot = rng.choice(slots)
            value = rng.choice(SLOT_VALUES[slot])
            text = f"If I were buying for a demo user, {value} for {slot} might fit; do not save that as my preference."
        else:
            text = rng.choice(GENERIC_CHATTER)
        return Observation(
            session_index=session_index,
            text=text,
            kind=f"distractor_{kind}",
            metadata={"is_profile_event": False},
        )

    def _questions(
        self,
        rng: random.Random,
        slots: list[str],
        final_profile: dict[str, str],
        last_profile_session: dict[str, int],
    ) -> tuple[Question, ...]:
        target_count = min(len(slots), self.config.profile_size)
        latest_allowed = self.config.session_count - self.config.delayed_query_horizon - 1
        observed_slots = [slot for slot in slots if last_profile_session[slot] >= 0]
        eligible_slots = [
            slot for slot in observed_slots if last_profile_session[slot] <= latest_allowed
        ]
        question_pool = eligible_slots or observed_slots
        question_slots = rng.sample(question_pool, min(target_count, len(question_pool)))
        questions: list[Question] = []
        for slot in question_slots:
            answer = final_profile[slot]
            distractors = [value for value in SLOT_VALUES[slot] if value != answer]
            rng.shuffle(distractors)
            choices = [answer, *distractors[: self.config.choices_per_question - 1]]
            rng.shuffle(choices)
            questions.append(
                Question(
                    slot=slot,
                    prompt=f"What is the user's latest preference for {slot}?",
                    choices=tuple(choices),
                    answer=answer,
                )
            )
        return tuple(questions)

    @staticmethod
    def _different_value(rng: random.Random, slot: str, old_value: str) -> str:
        candidates = [value for value in SLOT_VALUES[slot] if value != old_value]
        return rng.choice(candidates)

    @staticmethod
    def _memory_quality(notes: dict[str, str], final_profile: dict[str, str]) -> tuple[float, float]:
        if not notes:
            return (0.0, 0.0)
        correct_notes = 0
        for slot, value in final_profile.items():
            if notes.get(slot) == f"user prefers {value}":
                correct_notes += 1
        precision = correct_notes / len(notes)
        recall = correct_notes / len(final_profile)
        return (precision, recall)

    @staticmethod
    def _efficiency(note_tokens: int, note_budget: int) -> float:
        if note_tokens == 0:
            return 1.0
        used_fraction = min(1.0, note_tokens / note_budget)
        return 1.0 - 0.5 * used_fraction
