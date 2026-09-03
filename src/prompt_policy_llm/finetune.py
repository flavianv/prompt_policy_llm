"""JSONL formats for improving the prompt-policy controller."""

from __future__ import annotations

from .evaluation_types import group_by_problem
from .schema import EvalItem


CONTROLLER_SYSTEM_PROMPT = (
    "You are a prompt-policy controller. Given benchmark state, emit one short "
    "instruction of 30 tokens or fewer for a frozen solver."
)


def build_rollout_rows(items: list[EvalItem]) -> list[dict[str, object]]:
    """Create reward-labeled rows suitable for RL/GRPO-style controller training."""

    rows: list[dict[str, object]] = []
    baselines = {
        item.problem.id: item for item in items if item.mode == "baseline"
    }
    for item in items:
        if item.mode != "controlled":
            continue
        baseline = baselines.get(item.problem.id)
        baseline_score = baseline.score if baseline else 0.0
        rows.append(
            {
                "format": "prompt_policy_rollout_v1",
                "group_id": item.problem.id,
                "messages": [
                    {"role": "system", "content": CONTROLLER_SYSTEM_PROMPT},
                    {"role": "user", "content": item.controller_state},
                ],
                "action": item.instruction or "",
                "reward": item.score,
                "baseline_reward": baseline_score,
                "advantage": item.score - baseline_score,
                "metadata": item.metadata,
            }
        )
    return rows


def build_sft_rows(items: list[EvalItem]) -> list[dict[str, object]]:
    """Create chat-format seed rows from best observed controller actions."""

    rows: list[dict[str, object]] = []
    for problem_id, group in group_by_problem(items).items():
        controlled = [item for item in group if item.mode == "controlled" and item.instruction]
        if not controlled:
            continue
        best = max(controlled, key=lambda item: (item.score, -item.latency_s))
        rows.append(
            {
                "format": "controller_sft_chat_v1",
                "messages": [
                    {"role": "system", "content": CONTROLLER_SYSTEM_PROMPT},
                    {"role": "user", "content": best.controller_state},
                    {"role": "assistant", "content": best.instruction or ""},
                ],
                "metadata": {
                    **best.metadata,
                    "problem_id": problem_id,
                    "reward": best.score,
                },
            }
        )
    return rows

