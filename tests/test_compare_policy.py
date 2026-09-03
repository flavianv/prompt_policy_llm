from __future__ import annotations

from prompt_policy_llm.compare_policy import format_comparison
from prompt_policy_llm.schema import EvalItem, Problem


def test_format_comparison_shows_policy_output_reference_and_scores() -> None:
    problem = Problem(id="one", problem="What is 2 + 2?", answer="4")
    baseline = make_item(problem, mode="baseline", response="\\boxed{4}", score=1.0)
    controlled = make_item(
        problem,
        mode="controlled",
        response="\\boxed{4}",
        score=1.0,
        instruction="Check arithmetic; return one boxed answer.",
    )

    report = format_comparison(problem, baseline, controlled)

    assert "Baseline (no policy)" in report
    assert "Controlled (policy)" in report
    assert "Check arithmetic; return one boxed answer." in report
    assert "Reference answer" in report
    assert "Controller token budget: 7/30" in report


def make_item(
    problem: Problem,
    *,
    mode: str,
    response: str,
    score: float,
    instruction: str | None = None,
) -> EvalItem:
    return EvalItem(
        problem=problem,
        mode=mode,
        instruction=instruction,
        response=response,
        extracted_answer="4",
        score=score,
        latency_s=1.0,
        backend_latency_s=0.5,
        controller_latency_s=0.5 if instruction else 0.0,
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.00001,
        model="test",
        generation_status="completed",
        controller_model="controller" if instruction else "",
        controller_output_tokens=7 if instruction else 0,
        controller_token_budget=30 if instruction else 0,
    )
