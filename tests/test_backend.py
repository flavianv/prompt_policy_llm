from prompt_policy_llm.backend import (
    build_luna_prompt,
    build_solver_system_prompt,
    resolve_reasoning_effort,
)


def test_show_work_prompt_requests_derivation_and_boxed_answer() -> None:
    prompt = build_luna_prompt("What is 2 + 2?", show_work=True)

    assert "concise derivation" in prompt
    assert "\\boxed{}" in prompt
    assert "Do not include explanation" not in prompt
    assert "concise, verifiable derivation" in build_solver_system_prompt(show_work=True)


def test_answer_only_prompt_remains_the_default() -> None:
    prompt = build_luna_prompt("What is 2 + 2?")

    assert "Return only the final answer" in prompt
    assert "Do not include explanation" in prompt


def test_think_mode_overrides_legacy_reasoning_effort() -> None:
    assert resolve_reasoning_effort("none", "low") == "low"
    assert resolve_reasoning_effort("medium") == "medium"
