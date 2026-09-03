from __future__ import annotations

import json
from pathlib import Path

from prompt_policy_llm.evaluation import evaluate_problems
from prompt_policy_llm.schema import ControllerAction, Generation, Problem


class FakeBackend:
    def generate(self, problem: str, instruction: str | None = None) -> Generation:
        del problem
        answer = "1" if instruction else "0"
        return Generation(
            text=f"Final answer: \\boxed{{{answer}}}",
            latency_s=0.1,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.001,
            model="fake-luna",
            status="completed",
        )


class FakeController:
    def act(self, state: str, sample_index: int = 0) -> ControllerAction:
        del state
        instruction = f"sample instruction {sample_index}"
        return ControllerAction(
            instruction=instruction,
            output_tokens=3,
            token_budget=30,
            model="fake-controller",
            raw_text=instruction,
        )

    def instruct(self, state: str, sample_index: int = 0) -> str:
        del state
        return f"sample instruction {sample_index}"


def test_evaluate_problems_writes_predictions_and_training_rows(tmp_path: Path) -> None:
    problems = [
        Problem(id="p1", problem="What is 1?", answer="1", domain="algebra", difficulty=1.0)
    ]

    summary = evaluate_problems(
        problems=problems,
        backend=FakeBackend(),
        controller=FakeController(),
        output_dir=tmp_path,
        mode="both",
        controller_samples=2,
    )

    assert summary["num_predictions"] == 3
    assert summary["lift_over_baseline"] == 1.0

    predictions = (tmp_path / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    rollouts = (tmp_path / "controller_rollouts.jsonl").read_text(encoding="utf-8").splitlines()
    sft_rows = (tmp_path / "controller_sft_seed.jsonl").read_text(encoding="utf-8").splitlines()

    assert len(predictions) == 3
    assert len(rollouts) == 2
    assert len(sft_rows) == 1
    assert json.loads(rollouts[0])["format"] == "prompt_policy_rollout_v1"
    assert json.loads(sft_rows[0])["messages"][-1]["role"] == "assistant"
    controlled = json.loads(predictions[1])
    assert controlled["controller_model"] == "fake-controller"
    assert controlled["controller_output_tokens"] == 3
    assert controlled["controller_token_budget"] == 30
