# MVP Experiment Plan

## Hypothesis

A learned short-instruction controller can improve a frozen frontier model on verifiable tasks while adding less cost and latency than alternative multi-call or fine-tuning approaches.

## System

The system has two models:

- Controller: a small trainable LLM that emits a short instruction, capped at approximately 30 tokens.
- Back end: GPT-5.6 Luna, frozen throughout all experiments.

At inference time:

1. The benchmark item is converted into controller state.
2. The controller emits a steering instruction.
3. The steering instruction is composed with the task prompt.
4. GPT-5.6 Luna returns the final answer.
5. A verifier scores the answer.

## Controller Comparison

The first experimental sweep compares:

- 270M parameter controller
- 600M parameter controller
- 1.7B parameter controller

Each controller should use the same benchmark splits, reward definitions, prompt budget, back-end model, sampling settings, and reporting schema.

## Baselines

Use at least these baselines:

- Plain benchmark prompt with no controller.
- Static expert-written instruction with the same token budget as the controller.
- Random or ablated controller instruction, if practical, to measure whether learned instructions carry signal.

## Training

Start with a GRPO-style reinforcement learning loop:

- Sample multiple controller actions for each state.
- Run each action through the frozen back end.
- Score each final answer with the benchmark verifier.
- Estimate relative advantages inside the sampled group.
- Update only the controller.

The frontier model remains frozen in all experiments.

## Benchmarks

### LiveCodeBench

Measure coding problem correctness through official or reproducible verifiers. Track pass rate, retries if allowed, wall-clock latency, and total model cost.

### Omni-MATH Rule

Use rule-verifiable math items first. Track exact correctness, format failures, latency, and cost.

### ARC-AGI

Use verifier-driven ARC tasks. Track task accuracy, instruction patterns, latency, and cost.

## Metrics

Report the following for every controller size and benchmark:

- Accuracy or pass rate.
- Absolute lift over no-controller baseline.
- Relative lift over no-controller baseline.
- Median and p95 latency.
- Mean and total cost.
- Controller output token count.
- Back-end input and output token counts.
- Failure categories.

## Success Criteria

The MVP is promising if at least one controller size shows statistically credible lift over the no-controller baseline on a verifiable benchmark without unacceptable latency or cost overhead.

The MVP is strong if the learned controller beats the static same-budget instruction baseline across more than one benchmark.

## Later Domains

After verifiable benchmark success, extend to noisier environments:

- Shopping and product recommendation.
- Conversational recommendation.
- Research assistance.
- Multi-turn task support.

These domains will need proxy rewards, preference models, or human evaluation because correctness is less directly verifiable.

