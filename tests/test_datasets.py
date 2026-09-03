from prompt_policy_llm.datasets import filter_by_difficulty, problem_from_row
from prompt_policy_llm.schema import Problem


def test_problem_from_omnimath_rule_row() -> None:
    row = {
        "domain": ["Mathematics -> Algebra"],
        "difficulty": 8.0,
        "problem": "Find x.",
        "answer": "7",
        "source": "sample",
    }

    problem = problem_from_row(3, row)

    assert problem.id == "sample:3"
    assert problem.domain == "Mathematics -> Algebra"
    assert problem.difficulty == 8.0
    assert problem.answer == "7"


def test_filter_by_difficulty() -> None:
    problems = [
        Problem(id="easy", problem="a", answer="1", difficulty=2.0),
        Problem(id="hard", problem="b", answer="2", difficulty=8.0),
    ]

    filtered = filter_by_difficulty(problems, min_difficulty=None, max_difficulty=4)

    assert [problem.id for problem in filtered] == ["easy"]
