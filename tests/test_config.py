import pytest

from prompt_policy_llm import BenchmarkConfig, ControllerConfig


def test_controller_config_accepts_mvp_budget() -> None:
    config = ControllerConfig(name="controller-270m", parameters=270_000_000)

    config.validate()


def test_controller_config_rejects_large_instruction_budget() -> None:
    config = ControllerConfig(
        name="controller-270m",
        parameters=270_000_000,
        max_instruction_tokens=31,
    )

    with pytest.raises(ValueError, match="30-token"):
        config.validate()


def test_benchmark_config_requires_verifiable_benchmark() -> None:
    config = BenchmarkConfig(
        name="shopping",
        verifiable=False,
        primary_metric="preference_win_rate",
    )

    with pytest.raises(ValueError, match="automatic verifiers"):
        config.validate()

