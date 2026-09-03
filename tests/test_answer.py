from prompt_policy_llm.answer import (
    exact_match_score,
    extract_boxed_answer,
    extract_final_answer,
)


def test_extract_boxed_answer_uses_last_box() -> None:
    text = "First \\boxed{3}, then final \\boxed{5}."

    assert extract_boxed_answer(text) == "5"


def test_extract_boxed_answer_handles_nested_latex() -> None:
    text = "Final answer: \\boxed{\\frac{1}{2}}."

    assert extract_boxed_answer(text) == "\\frac{1}{2}"


def test_extract_final_answer_falls_back_to_last_number() -> None:
    assert extract_final_answer("After work, the answer is 42.") == "42"


def test_exact_match_normalizes_commas_and_spaces() -> None:
    assert exact_match_score("  115,440 ", "115440") == 1.0


def test_exact_match_normalizes_fraction_macros() -> None:
    assert exact_match_score("\\dfrac{1}{2}", "\\frac{1}{2}") == 1.0
