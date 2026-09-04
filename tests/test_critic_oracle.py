from __future__ import annotations

from pathlib import Path

from prompt_policy_llm.critic_oracle import TextCheck, check_no_answer_leak, run_critic_oracle
from prompt_policy_llm.schema import Generation, Problem


class FakeAnswerer:
    def generate(self, problem: str, instruction: str | None = None) -> Generation:
        answer = "1" if instruction else "0"
        return Generation(
            text=f"\\boxed{{{answer}}}", latency_s=0.1, input_tokens=1, output_tokens=1,
            cost_usd=0.01, model="fake", status="completed"
        )


class FakeRoles:
    def __init__(self, leak: bool = False) -> None:
        self.leak = leak

    def generate(self, system: str, user: str) -> Generation:
        del user
        text = "Use a variable and form the equation."
        if "critic" in system.lower():
            text = "rating: 4\nfailure: missing-constraint\nrepair: Check the constraint before simplifying."
        if self.leak and "critic" in system.lower():
            text = "The final answer is 1."
        return Generation(text=text, latency_s=0.1, input_tokens=1, output_tokens=1, cost_usd=0.01, model="fake", status="completed")


def test_critic_oracle_records_a_paired_oracle_win(tmp_path: Path) -> None:
    metrics = run_critic_oracle([Problem(id="one", problem="test", answer="1")], FakeAnswerer(), FakeRoles(), tmp_path)

    assert metrics["arm_a_direct_think_correct"] == 0
    assert metrics["arm_b_oracle_critic_correct"] == 1
    assert metrics["paired"]["oracle_only_wins"] == 1
    assert (tmp_path / "critic_oracle_traces.txt").exists()


def test_answer_leak_blocks_executor(tmp_path: Path) -> None:
    metrics = run_critic_oracle([Problem(id="one", problem="test", answer="1")], FakeAnswerer(), FakeRoles(leak=True), tmp_path)

    assert metrics["arm_b_oracle_critic_correct"] == 0
    assert metrics["arm_b_critic_leak_or_format_blocks"] == 1


def test_leak_check_rejects_reference_answer() -> None:
    check = check_no_answer_leak(
        Generation(text="Use the value 42 in the equation.", latency_s=0.0, input_tokens=0, output_tokens=0, cost_usd=0.0, model="fake", status="completed"),
        expected_answer="42",
        max_words=30,
    )

    assert check == TextCheck(False, "contains reference answer", "[REDACTED: answer leak]")
