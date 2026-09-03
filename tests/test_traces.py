from __future__ import annotations

from prompt_policy_llm.schema import EvalItem, Problem
from prompt_policy_llm.traces import format_trace_rows, write_trace_report


def test_trace_report_has_problem_hint_outputs_answers_and_scores(tmp_path) -> None:
    problem = Problem(id="one", problem="What is 2 + 2?", answer="4", source="test")
    baseline = make_item(problem, "baseline", "\\boxed{4}", None, 1.0)
    controlled = make_item(
        problem,
        "controlled",
        "\\boxed{4}",
        "Check arithmetic and return one boxed answer.",
        1.0,
    )

    path = tmp_path / "traces.txt"
    write_trace_report(path, [baseline, controlled])
    report = path.read_text(encoding="utf-8")

    assert "What is 2 + 2?" in report
    assert "Policy hint: Check arithmetic" in report
    assert "Raw solver output:" in report
    assert "Final answer extracted: 4" in report
    assert "Reference answer: 4" in report
    assert report.count("Exact-match score: 1") == 2
    assert format_trace_rows([]) == ""


def make_item(
    problem: Problem,
    mode: str,
    response: str,
    instruction: str | None,
    score: float,
) -> EvalItem:
    return EvalItem(
        problem=problem,
        mode=mode,
        instruction=instruction,
        response=response,
        extracted_answer="4",
        score=score,
        latency_s=1.0,
        backend_latency_s=1.0,
        controller_latency_s=0.0,
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
        model="test",
        generation_status="completed",
        controller_model="test-controller" if instruction else "",
        controller_output_tokens=8 if instruction else 0,
        controller_token_budget=30 if instruction else 0,
    )
