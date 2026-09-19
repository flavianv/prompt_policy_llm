"""Configuration primitives for prompt-policy experiments."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ControllerConfig:
    """Configuration for a trainable prompt-policy controller."""

    name: str
    parameters: int
    max_instruction_tokens: int = 30
    trainable: bool = True

    def validate(self) -> None:
        if self.parameters <= 0:
            raise ValueError("controller parameters must be positive")
        if self.max_instruction_tokens <= 0:
            raise ValueError("max instruction tokens must be positive")
        if self.max_instruction_tokens > 30:
            raise ValueError("MVP controllers must stay within the 30-token instruction budget")


@dataclass(frozen=True)
class BenchmarkConfig:
    """Configuration for a benchmark with an automatic verifier."""

    name: str
    verifiable: bool
    primary_metric: str

    def validate(self) -> None:
        if not self.name:
            raise ValueError("benchmark name is required")
        if not self.primary_metric:
            raise ValueError("primary metric is required")
        if not self.verifiable:
            raise ValueError("MVP benchmarks must have automatic verifiers")

