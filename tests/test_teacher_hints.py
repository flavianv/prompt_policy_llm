from __future__ import annotations

from pathlib import Path
import json

from prompt_policy_llm.schema import Generation, Problem
from prompt_policy_llm.teacher_hints import (
    LocalHintGenerator,
    ParsedHint,
    TeacherCall,
    build_teacher_prompt,
    generate_teacher_data,
    load_cached_hint_teacher,
    parse_teacher_hints,
)
from prompt_policy_llm.local_hints import (
    LFM2_350M_MATH_MODEL,
    build_local_hint_prompt,
    resolve_local_hint_model,
)


class FakeBackend:
    def generate(self, problem: str, instruction: str | None = None) -> Generation:
        answer = "1" if instruction else "0"
        return Generation(
            text=f"\\boxed{{{answer}}}",
            latency_s=0.1,
            input_tokens=10,
            output_tokens=2,
            cost_usd=0.01,
            model="fake-luna",
            status="completed",
        )


class FakeTeacher:
    def propose(self, problem: Problem, baseline, candidates: int) -> TeacherCall:
        del problem, baseline, candidates
        return TeacherCall(
            generation=Generation(
                text="Use an invariant, then check the algebra.",
                latency_s=0.2,
                input_tokens=20,
                output_tokens=8,
                cost_usd=0.02,
                model="fake-teacher",
                status="completed",
            ),
            accepted=[ParsedHint("Use an invariant, then check the algebra.", 7)],
            rejected=[],
        )


def test_parse_teacher_hints_rejects_answer_leakage_and_over_budget() -> None:
    accepted, rejected = parse_teacher_hints(
        "Use a parity invariant before solving.\nThe final answer is 42.\n"
        + "word " * 31,
        expected_answer="42",
        candidates=2,
    )

    assert [hint.instruction for hint in accepted] == ["Use a parity invariant before solving."]
    assert any(hint.reason == "answer-revealing language" for hint in rejected)
    assert any("over 30-token" in hint.reason for hint in rejected)


def test_answer_aware_teacher_gets_reference_for_private_checking() -> None:
    problem = Problem(id="one", problem="A test problem", answer="42")
    baseline = generate_baseline(problem)

    teacher_prompt = build_teacher_prompt(problem, baseline, candidates=1, answer_aware=True)

    assert "Trusted verifier answer" in teacher_prompt
    assert "42" in teacher_prompt
    assert "target 8 to 16 tokens" in teacher_prompt
    assert "exceed 30 tokens" in teacher_prompt


def test_normal_api_teacher_prompt_withholds_luna_output_and_reference() -> None:
    problem = Problem(id="one", problem="A test problem", answer="42")
    baseline = generate_baseline(problem)

    teacher_prompt = build_teacher_prompt(problem, baseline, candidates=1)

    assert "Trusted verifier answer" not in teacher_prompt
    assert "42" not in teacher_prompt
    assert "extracted answer" not in teacher_prompt
    assert "Baseline attempt metadata" not in teacher_prompt


def test_local_lfm_prompt_withholds_trusted_and_baseline_answers() -> None:
    problem = Problem(id="one", problem="What is 6 times 7?", answer="42")
    baseline = generate_baseline(problem)

    prompt = build_local_hint_prompt(problem, baseline, candidates=1)

    assert resolve_local_hint_model("lfm2-350m-math") == LFM2_350M_MATH_MODEL
    assert "42" not in prompt
    assert "target 8 to 16 tokens" in prompt
    assert "never exceed 30 tokens" in prompt


def test_local_hint_adapter_uses_the_existing_leak_parser() -> None:
    problem = Problem(id="one", problem="A test problem", answer="42")
    baseline = generate_baseline(problem)

    class FakeLocalProvider:
        def propose(self, problem: Problem, baseline, candidates: int) -> Generation:
            del problem, baseline, candidates
            return Generation(
                text="Use the final answer 42.",
                latency_s=0.0,
                input_tokens=1,
                output_tokens=5,
                cost_usd=0.0,
                model="LiquidAI/LFM2-350M-Math@cpu",
                status="completed",
            )

    call = LocalHintGenerator("lfm2-350m-math", provider=FakeLocalProvider()).propose(
        problem, baseline, candidates=1
    )

    assert not call.accepted
    assert any(item.reason == "answer-revealing language" for item in call.rejected)


def test_incomplete_teacher_response_is_rejected() -> None:
    from prompt_policy_llm.teacher_hints import finalize_teacher_call

    call = finalize_teacher_call(
        Generation(
            text="Use a parity invariant before solving.",
            latency_s=0.0,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            model="fake-teacher",
            status="incomplete",
            incomplete_reason="max_output_tokens",
        ),
        expected_answer="42",
        candidates=1,
    )

    assert not call.accepted
    assert any("teacher response incomplete" in hint.reason for hint in call.rejected)


def generate_baseline(problem: Problem):
    from prompt_policy_llm.evaluation import evaluate_one

    return evaluate_one(problem, FakeBackend(), instruction=None, mode="baseline")


def test_generate_teacher_data_writes_flip_only_training_rows(tmp_path: Path) -> None:
    problem = Problem(id="one", problem="A test problem", answer="1")
    summary = generate_teacher_data(
        problems=[problem],
        backend=FakeBackend(),
        teacher=FakeTeacher(),
        output_dir=tmp_path,
        candidates=1,
    )

    assert summary["baseline_wrong_to_hinted_correct_flips"] == 1
    assert summary["teacher_calls"] == 1
    assert (tmp_path / "teacher_flips_sft.jsonl").read_text(encoding="utf-8")
    assert (tmp_path / "verified_teacher_candidates.jsonl").read_text(encoding="utf-8")
    assert "leak check: passed_teacher_hint_parser" in (
        tmp_path / "teacher_oracle_traces.txt"
    ).read_text(encoding="utf-8")


def test_current_failure_target_does_not_relax_a_shortage(tmp_path: Path) -> None:
    wrong = Problem(id="wrong", problem="A test problem", answer="1")
    correct = Problem(id="correct", problem="A second problem", answer="0")
    summary = generate_teacher_data(
        problems=[wrong, correct],
        backend=FakeBackend(),
        teacher=FakeTeacher(),
        output_dir=tmp_path,
        candidates=1,
        target_baseline_failures=2,
    )

    assert summary["current_baseline_failures_found"] == 1
    assert summary["current_failure_shortage"] == 1
    assert summary["teacher_calls"] == 0
    assert summary["verified_candidates"] == 0


def test_cached_hint_teacher_revalidates_exact_source_hint(tmp_path: Path) -> None:
    problem = Problem(id="one", problem="A test problem", answer="1")
    source = tmp_path / "teacher_proposals.jsonl"
    hint = "Use an invariant, then check the algebra."
    source.write_text(
        json.dumps(
            {
                "problem_id": "one",
                "teacher": {"model": "gpt-5.6-sol", "raw_output": hint},
                "accepted_hints": [{"instruction": hint, "output_tokens": 7}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    teacher, provenance = load_cached_hint_teacher(source, [problem], candidates=1)
    call = teacher.propose(problem, generate_baseline(problem), candidates=1)

    assert call.accepted[0].instruction == hint
    assert provenance[0]["identical"]
    assert provenance[0]["source_hint_sha256"] == provenance[0]["replay_hint_sha256"]
