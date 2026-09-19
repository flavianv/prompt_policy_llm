"""Command line interface for AdaptGym v0."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from adaptgym.baselines import POLICIES
from adaptgym.config import DEFAULT_DISTRACTOR_TYPES, DifficultyConfig
from adaptgym.environment import AdaptGymEnv


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="adaptgym-v0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run one deterministic AdaptGym v0 episode")
    run.add_argument("--policy", choices=sorted(POLICIES), default="naive")
    run.add_argument("--profile-size", type=int, default=DifficultyConfig.profile_size)
    run.add_argument("--session-count", type=int, default=DifficultyConfig.session_count)
    run.add_argument("--distractors-per-session", type=int, default=DifficultyConfig.distractors_per_session)
    run.add_argument("--distractor-types", default=",".join(DEFAULT_DISTRACTOR_TYPES))
    run.add_argument("--lexical-similarity", type=float, default=DifficultyConfig.lexical_similarity)
    run.add_argument("--update-rate", type=float, default=DifficultyConfig.update_rate)
    run.add_argument("--delayed-query-horizon", type=int, default=DifficultyConfig.delayed_query_horizon)
    run.add_argument("--note-budget", type=int, default=DifficultyConfig.note_budget)
    run.add_argument("--choices-per-question", type=int, default=DifficultyConfig.choices_per_question)
    run.add_argument("--seed", type=int, default=DifficultyConfig.seed)
    run.add_argument("--show-trace", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "run":
        result = _run(args)
        print(json.dumps(result, indent=2, sort_keys=True))


def _run(args: argparse.Namespace) -> dict[str, object]:
    config = DifficultyConfig(
        profile_size=args.profile_size,
        session_count=args.session_count,
        distractors_per_session=args.distractors_per_session,
        distractor_types=tuple(item.strip() for item in args.distractor_types.split(",") if item.strip()),
        lexical_similarity=args.lexical_similarity,
        update_rate=args.update_rate,
        delayed_query_horizon=args.delayed_query_horizon,
        note_budget=args.note_budget,
        choices_per_question=args.choices_per_question,
        seed=args.seed,
    )
    env = AdaptGymEnv(config)
    episode = env.generate_episode()
    policy = POLICIES[args.policy]()
    evaluation = env.evaluate_policy(policy, episode)
    payload: dict[str, object] = {
        "policy": evaluation.policy_name,
        "config": episode.config,
        "score": asdict(evaluation.score),
        "notes": evaluation.notes,
        "questions": [
            {
                "prompt": question.prompt,
                "choices": list(question.choices),
                "answer": question.answer,
                "policy_answer": answer,
            }
            for question, answer in zip(episode.questions, evaluation.answers)
        ],
    }
    if args.show_trace:
        payload["trace"] = [
            {
                "session_index": observation.session_index,
                "kind": observation.kind,
                "text": observation.text,
                "action": asdict(action),
            }
            for observation, action in zip(episode.observations, evaluation.actions)
        ]
    return payload


if __name__ == "__main__":
    main()
