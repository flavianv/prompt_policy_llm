"""Generate verified teacher-hint data for the prompt-policy controller."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .answer import normalize_answer
from .backend import (
    LUNA_INPUT_USD_PER_MTOK,
    LUNA_OUTPUT_USD_PER_MTOK,
    THINK_MODE_CHOICES,
    LunaBackend,
    LunaConfig,
    extract_response_text,
    resolve_reasoning_effort,
)
from .datasets import OMNI_MATH_RULE_URL, load_omni_math_rule
from .evaluation import build_controller_state, evaluate_one
from .finetune import CONTROLLER_SYSTEM_PROMPT
from .local_hints import (
    LFM2_HINT_MODEL_ALIAS,
    LocalHintConfig,
    LocalLFMHintProvider,
    resolve_local_hint_model,
)
from .schema import EvalItem, Generation, Problem


DEFAULT_TEACHER_MODEL = "gpt-5.6-terra"
PREFERRED_HINT_TOKEN_RANGE = "8 to 16"
MODEL_PRICING_USD_PER_MTOK = {
    "gpt-5.6-luna": (LUNA_INPUT_USD_PER_MTOK, LUNA_OUTPUT_USD_PER_MTOK),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-sol": (4.00, 20.00),
}


@dataclass(frozen=True)
class TeacherConfig:
    model: str = DEFAULT_TEACHER_MODEL
    max_output_tokens: int = 128
    reasoning_effort: str = "none"
    answer_aware: bool = False


@dataclass(frozen=True)
class ParsedHint:
    instruction: str
    output_tokens: int


@dataclass(frozen=True)
class RejectedHint:
    text: str
    reason: str


@dataclass(frozen=True)
class TeacherCall:
    generation: Generation
    accepted: list[ParsedHint]
    rejected: list[RejectedHint]


class TeacherProtocol(Protocol):
    def propose(self, problem: Problem, baseline: EvalItem, candidates: int) -> TeacherCall:
        ...


class TeacherHintGenerator:
    """OpenAI Responses API wrapper for a selectable teacher, including Luna."""

    def __init__(self, config: TeacherConfig | None = None, dry_run: bool = False) -> None:
        self.config = config or TeacherConfig()
        self.dry_run = dry_run
        self._client: Any | None = None

    def propose(self, problem: Problem, baseline: EvalItem, candidates: int) -> TeacherCall:
        if candidates < 1:
            raise ValueError("candidates must be at least 1")
        if self.dry_run:
            return self._dry_propose(candidates)

        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "input": [
                {"role": "system", "content": teacher_system_prompt(self.config.answer_aware)},
                {
                    "role": "user",
                    "content": build_teacher_prompt(
                        problem, baseline, candidates, answer_aware=self.config.answer_aware
                    ),
                },
            ],
            "max_output_tokens": self.config.max_output_tokens,
        }
        if self.config.reasoning_effort != "none":
            kwargs["reasoning"] = {"effort": self.config.reasoning_effort}

        started = time.perf_counter()
        response = self._client.responses.create(**kwargs)
        latency_s = time.perf_counter() - started
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        generation = Generation(
            text=extract_response_text(response),
            latency_s=latency_s,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_teacher_cost(self.config.model, input_tokens, output_tokens),
            model=self.config.model,
            status=str(getattr(response, "status", "") or ""),
            incomplete_reason=str(
                getattr(getattr(response, "incomplete_details", None), "reason", "") or ""
            ),
        )
        return finalize_teacher_call(generation, problem.answer, candidates)

    def _dry_propose(self, candidates: int) -> TeacherCall:
        hints = [
            "Identify the governing invariant before computing.",
            "Check edge cases, then verify the final algebra.",
            "Translate the constraints into an equation before solving.",
            "Use modular structure and validate each case.",
        ][:candidates]
        text = "\n".join(hints)
        generation = Generation(
            text=text,
            latency_s=0.0,
            input_tokens=80,
            output_tokens=sum(len(hint.split()) for hint in hints),
            cost_usd=estimate_teacher_cost(
                self.config.model, 80, sum(len(hint.split()) for hint in hints)
            ),
            model=f"{self.config.model}:dry-run",
            status="completed",
        )
        return finalize_teacher_call(generation, "", candidates)


class LocalHintGenerator:
    """Adapter that exposes the local LFM2 hint model through the teacher protocol."""

    def __init__(
        self,
        model_name: str,
        device: str = "auto",
        provider: LocalLFMHintProvider | None = None,
    ) -> None:
        self.provider = provider or LocalLFMHintProvider(
            LocalHintConfig(model=resolve_local_hint_model(model_name), device=device)
        )

    def propose(self, problem: Problem, baseline: EvalItem, candidates: int) -> TeacherCall:
        return finalize_teacher_call(self.provider.propose(problem, baseline, candidates), problem.answer, candidates)


class CachedHintTeacher:
    """Replay previously accepted hints without making a new teacher-model call."""

    def __init__(self, calls: dict[str, TeacherCall]) -> None:
        self.calls = calls

    def propose(self, problem: Problem, baseline: EvalItem, candidates: int) -> TeacherCall:
        del baseline
        call = self.calls.get(problem.id)
        if call is None:
            raise ValueError(f"cached hints missing requested problem: {problem.id}")
        if len(call.accepted) != candidates:
            raise ValueError(
                f"cached hints for {problem.id} contain {len(call.accepted)} accepted hints; requested {candidates}"
            )
        return call


def estimate_teacher_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = MODEL_PRICING_USD_PER_MTOK.get(
        model, MODEL_PRICING_USD_PER_MTOK[DEFAULT_TEACHER_MODEL]
    )
    return (
        input_tokens * input_price / 1_000_000
        + output_tokens * output_price / 1_000_000
    )


def teacher_system_prompt(answer_aware: bool = False) -> str:
    prompt = (
        "You curate supervision for a prompt-policy controller. Produce only compact, "
        "answer-blind solver instructions. Never reveal, calculate, quote, encode, or "
        "state the final answer. Never copy problem text, names, labels, or numbers."
    )
    if answer_aware:
        prompt += " Use the trusted reference answer only for private checking before writing the hint."
    return prompt


def build_teacher_prompt(
    problem: Problem,
    baseline: EvalItem,
    candidates: int,
    answer_aware: bool = False,
) -> str:
    del baseline
    prompt = (
        f"Propose exactly {candidates} diverse controller hints for this math problem. "
        f"Each hint must be one line, target {PREFERRED_HINT_TOKEN_RANGE} tokens, and never "
        "exceed 30 tokens. Describe one useful solving tactic only. Do not state a final "
        "answer or include an answer-like number.\n\n"
        f"Problem:\n{problem.problem}\n\n"
        "Return plain hint lines only."
    )
    if answer_aware:
        prompt += (
            "\n\nTrusted verifier answer (private checking only; never repeat, transform, "
            f"or encode it in a hint):\n{problem.answer}"
        )
    return prompt


def parse_teacher_hints(
    text: str,
    expected_answer: str,
    candidates: int,
) -> tuple[list[ParsedHint], list[RejectedHint]]:
    """Parse one-line hints and reject likely answer leakage or over-budget output."""

    accepted: list[ParsedHint] = []
    rejected: list[RejectedHint] = []
    seen: set[str] = set()
    expected = normalize_answer(expected_answer).lower()
    for raw_line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line).strip()
        reason = validate_hint(line, expected, seen)
        if reason:
            rejected.append(RejectedHint(text=raw_line, reason=reason))
            continue
        seen.add(line.lower())
        accepted.append(ParsedHint(instruction=line, output_tokens=len(line.split())))
        if len(accepted) == candidates:
            break
    if len(accepted) < candidates:
        rejected.append(
            RejectedHint(
                text="",
                reason=f"teacher returned {len(accepted)} valid hints; requested {candidates}",
            )
        )
    return accepted, rejected


def finalize_teacher_call(
    generation: Generation,
    expected_answer: str,
    candidates: int,
) -> TeacherCall:
    accepted, rejected = parse_teacher_hints(generation.text, expected_answer, candidates)
    if generation.status and generation.status != "completed":
        rejected.append(
            RejectedHint(
                text=generation.text,
                reason=f"teacher response incomplete: {generation.incomplete_reason or generation.status}",
            )
        )
        accepted = []
    return TeacherCall(generation=generation, accepted=accepted, rejected=rejected)


def validate_hint(text: str, expected_answer: str, seen: set[str]) -> str | None:
    if len(text.split()) < 3:
        return "fewer than three words"
    if len(text.split()) > 30:
        return "over 30-token whitespace budget"
    lowered = text.lower()
    if lowered in seen:
        return "duplicate hint"
    forbidden = ("\\boxed", "final answer", "the answer is", "answer:", "solution:")
    if any(fragment in lowered for fragment in forbidden):
        return "answer-revealing language"
    normalized = normalize_answer(text).lower()
    if expected_answer and expected_answer in normalized:
        return "contains the reference answer"
    return None


def load_baseline_items(path: Path, problems: list[Problem]) -> dict[str, EvalItem]:
    problem_by_id = {problem.id: problem for problem in problems}
    baselines: dict[str, EvalItem] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("mode") != "baseline":
                continue
            problem = problem_by_id.get(str(row["problem_id"]))
            if problem is None or problem.id in baselines:
                continue
            baselines[problem.id] = eval_item_from_row(problem, row)
    missing = [problem.id for problem in problems if problem.id not in baselines]
    if missing:
        raise ValueError(f"baseline predictions missing {len(missing)} requested problems")
    return baselines


def load_cached_hint_teacher(
    path: Path,
    problems: list[Problem],
    candidates: int,
) -> tuple[CachedHintTeacher, list[dict[str, object]]]:
    """Load and revalidate accepted source hints, retaining identity provenance."""

    rows_by_id: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                problem_id = str(row.get("problem_id", ""))
                if problem_id and problem_id not in rows_by_id:
                    rows_by_id[problem_id] = row

    calls: dict[str, TeacherCall] = {}
    provenance: list[dict[str, object]] = []
    for problem in problems:
        row = rows_by_id.get(problem.id)
        if row is None:
            raise ValueError(f"cached hints missing requested problem: {problem.id}")
        teacher = dict(row.get("teacher", {}))
        raw_output = str(teacher.get("raw_output", ""))
        accepted, rejected = parse_teacher_hints(raw_output, problem.answer, candidates)
        saved_hints = [str(item.get("instruction", "")) for item in row.get("accepted_hints", [])]
        parsed_hints = [item.instruction for item in accepted]
        if rejected or parsed_hints != saved_hints or len(parsed_hints) != candidates:
            raise ValueError(
                f"cached hint identity or leak validation failed for {problem.id}; refusing replay"
            )
        generation = Generation(
            text=raw_output,
            latency_s=0.0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model=f"{teacher.get('model', 'unknown')}:cached",
            status="completed",
        )
        calls[problem.id] = TeacherCall(generation=generation, accepted=accepted, rejected=[])
        provenance.append(
            {
                "problem_id": problem.id,
                "source_hint": saved_hints[0],
                "replay_hint": parsed_hints[0],
                "identical": saved_hints == parsed_hints,
                "source_hint_sha256": hashlib.sha256(saved_hints[0].encode("utf-8")).hexdigest(),
                "replay_hint_sha256": hashlib.sha256(parsed_hints[0].encode("utf-8")).hexdigest(),
            }
        )
    return CachedHintTeacher(calls), provenance


def eval_item_from_row(problem: Problem, row: dict[str, Any]) -> EvalItem:
    return EvalItem(
        problem=problem,
        mode="baseline",
        instruction=None,
        response=str(row.get("response", "")),
        extracted_answer=str(row.get("extracted_answer", "")),
        score=float(row.get("score", 0.0)),
        latency_s=float(row.get("latency_s", 0.0)),
        backend_latency_s=float(row.get("backend_latency_s", row.get("latency_s", 0.0))),
        controller_latency_s=0.0,
        input_tokens=int(row.get("input_tokens", 0)),
        output_tokens=int(row.get("output_tokens", 0)),
        cost_usd=float(row.get("cost_usd", 0.0)),
        model=str(row.get("model", "")),
        generation_status=str(row.get("generation_status", "")),
        incomplete_reason=str(row.get("incomplete_reason", "")),
    )


def generate_teacher_data(
    problems: list[Problem],
    backend: LunaBackend,
    teacher: TeacherProtocol,
    output_dir: Path,
    candidates: int,
    teacher_on_all: bool = False,
    supplied_baselines: dict[str, EvalItem] | None = None,
    target_baseline_failures: int | None = None,
) -> dict[str, object]:
    """Produce verified candidate hints and flip-only training examples, never training."""

    if candidates < 1:
        raise ValueError("candidates must be at least 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    baselines: list[EvalItem] = []
    teacher_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    flip_rows: list[dict[str, object]] = []
    started = time.perf_counter()

    for problem in problems:
        baseline = supplied_baselines[problem.id] if supplied_baselines else evaluate_one(
            problem, backend, instruction=None, mode="baseline"
        )
        baselines.append(baseline)

    selected_baseline_ids: set[str] | None = None
    failure_shortage = 0
    if target_baseline_failures is not None:
        failures = [item for item in baselines if item.score < 1.0]
        if len(failures) < target_baseline_failures:
            failure_shortage = target_baseline_failures - len(failures)
            selected_baseline_ids = set()
        else:
            selected_baseline_ids = {item.problem.id for item in failures[:target_baseline_failures]}

    for baseline in baselines:
        problem = baseline.problem
        if selected_baseline_ids is not None and problem.id not in selected_baseline_ids:
            continue
        if not teacher_on_all and baseline.score >= 1.0:
            continue

        call = teacher.propose(problem, baseline, candidates)
        call_index = len(teacher_rows)
        teacher_rows.append(teacher_row(problem, baseline, call, call_index))
        for candidate_index, hint in enumerate(call.accepted):
            hinted = evaluate_one(
                problem,
                backend,
                instruction=hint.instruction,
                mode="teacher-hinted",
                sample_index=candidate_index,
            )
            row = verified_candidate_row(problem, baseline, call, call_index, hint, candidate_index, hinted)
            candidate_rows.append(row)
            if baseline.score < 1.0 and hinted.score >= 1.0:
                flip_rows.append(flip_training_row(problem, baseline, call, call_index, hint, hinted))

    paths = {
        "baselines": output_dir / "baselines.jsonl",
        "teacher_proposals": output_dir / "teacher_proposals.jsonl",
        "verified_candidates": output_dir / "verified_teacher_candidates.jsonl",
        "flip_sft": output_dir / "teacher_flips_sft.jsonl",
        "traces": output_dir / "teacher_oracle_traces.txt",
        "metrics": output_dir / "metrics.json",
    }
    write_jsonl(paths["baselines"], [item.to_json() for item in baselines])
    write_jsonl(paths["teacher_proposals"], teacher_rows)
    write_jsonl(paths["verified_candidates"], candidate_rows)
    write_jsonl(paths["flip_sft"], flip_rows)
    write_teacher_trace_report(paths["traces"], teacher_rows, candidate_rows)
    summary = summarize_teacher_data(baselines, teacher_rows, candidate_rows, flip_rows)
    if target_baseline_failures is not None:
        summary["target_baseline_failures"] = target_baseline_failures
        summary["current_baseline_failures_found"] = sum(item.score < 1.0 for item in baselines)
        summary["selected_current_baseline_failures"] = len(selected_baseline_ids or set())
        summary["current_failure_shortage"] = failure_shortage
    summary["wall_time_s"] = round(time.perf_counter() - started, 6)
    summary["paths"] = {name: str(path) for name, path in paths.items()}
    paths["metrics"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def teacher_row(problem: Problem, baseline: EvalItem, call: TeacherCall, call_index: int) -> dict[str, object]:
    return {
        "format": "teacher_hint_proposal_v1",
        "teacher_call_index": call_index,
        "problem_id": problem.id,
        "problem": problem.problem,
        "reference_answer": problem.answer,
        "baseline": baseline.to_json(),
        "teacher": {
            "model": call.generation.model,
            "status": call.generation.status,
            "incomplete_reason": call.generation.incomplete_reason,
            "latency_s": call.generation.latency_s,
            "input_tokens": call.generation.input_tokens,
            "output_tokens": call.generation.output_tokens,
            "cost_usd": call.generation.cost_usd,
            "raw_output": call.generation.text,
        },
        "accepted_hints": [hint.__dict__ for hint in call.accepted],
        "rejected_hints": [hint.__dict__ for hint in call.rejected],
    }


def verified_candidate_row(
    problem: Problem,
    baseline: EvalItem,
    call: TeacherCall,
    call_index: int,
    hint: ParsedHint,
    candidate_index: int,
    hinted: EvalItem,
) -> dict[str, object]:
    return {
        "format": "teacher_verified_controller_candidate_v1",
        "teacher_call_index": call_index,
        "candidate_index": candidate_index,
        "problem_id": problem.id,
        "state": build_controller_state(problem),
        "hint": hint.instruction,
        "hint_tokens": hint.output_tokens,
        "teacher_model": call.generation.model,
        "leak_check": "passed_teacher_hint_parser",
        "baseline": baseline.to_json(),
        "hinted": hinted.to_json(),
        "baseline_wrong_to_hinted_correct": baseline.score < 1.0 and hinted.score >= 1.0,
        "training_selection": (
            "accepted_baseline_wrong_to_hinted_correct"
            if baseline.score < 1.0 and hinted.score >= 1.0
            else "rejected_by_verifier"
        ),
    }


def flip_training_row(
    problem: Problem,
    baseline: EvalItem,
    call: TeacherCall,
    call_index: int,
    hint: ParsedHint,
    hinted: EvalItem,
) -> dict[str, object]:
    return {
        "format": "controller_sft_chat_v1",
        "messages": [
            {"role": "system", "content": CONTROLLER_SYSTEM_PROMPT},
            {"role": "user", "content": build_controller_state(problem)},
            {"role": "assistant", "content": hint.instruction},
        ],
        "metadata": {
            "selection": "baseline_wrong_to_hinted_correct",
            "teacher_call_index": call_index,
            "teacher_model": call.generation.model,
            "problem_id": problem.id,
            "baseline_reward": baseline.score,
            "reward": hinted.score,
            "advantage": hinted.score - baseline.score,
            "hint_tokens": hint.output_tokens,
            "expected_answer": problem.answer,
        },
    }


def summarize_teacher_data(
    baselines: list[EvalItem],
    teacher_rows: list[dict[str, object]],
    candidate_rows: list[dict[str, object]],
    flip_rows: list[dict[str, object]],
) -> dict[str, object]:
    teacher_cost = sum(float(row["teacher"]["cost_usd"]) for row in teacher_rows)
    solver_candidate_cost = sum(float(row["hinted"]["cost_usd"]) for row in candidate_rows)
    paired = {
        "hint_only_wins": sum(
            float(row["baseline"]["score"]) == 0 and float(row["hinted"]["score"]) == 1
            for row in candidate_rows
        ),
        "baseline_only_wins": sum(
            float(row["baseline"]["score"]) == 1 and float(row["hinted"]["score"]) == 0
            for row in candidate_rows
        ),
        "both_correct": sum(
            float(row["baseline"]["score"]) == 1 and float(row["hinted"]["score"]) == 1
            for row in candidate_rows
        ),
        "both_wrong": sum(
            float(row["baseline"]["score"]) == 0 and float(row["hinted"]["score"]) == 0
            for row in candidate_rows
        ),
    }
    return {
        "num_problems": len(baselines),
        "baseline_accuracy": average([item.score for item in baselines]),
        "teacher_calls": len(teacher_rows),
        "teacher_proposals_accepted": sum(len(row["accepted_hints"]) for row in teacher_rows),
        "teacher_proposals_rejected": sum(len(row["rejected_hints"]) for row in teacher_rows),
        "verified_candidates": len(candidate_rows),
        "hinted_candidate_accuracy": average(
            [float(row["hinted"]["score"]) for row in candidate_rows]
        ),
        "baseline_wrong_to_hinted_correct_flips": len(flip_rows),
        "rejected_by_verifier": len(candidate_rows) - len(flip_rows),
        "paired": paired,
        "baseline_solver_cost_usd": sum(item.cost_usd for item in baselines),
        "teacher_cost_usd": teacher_cost,
        "hinted_solver_cost_usd": solver_candidate_cost,
        "total_cost_usd": sum(item.cost_usd for item in baselines)
        + teacher_cost
        + solver_candidate_cost,
    }


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_teacher_trace_report(
    path: Path,
    teacher_rows: list[dict[str, object]],
    candidate_rows: list[dict[str, object]],
) -> None:
    candidates_by_call: dict[int, list[dict[str, object]]] = {}
    for row in candidate_rows:
        candidates_by_call.setdefault(int(row["teacher_call_index"]), []).append(row)
    sections: list[str] = []
    for proposal in teacher_rows:
        call_index = int(proposal["teacher_call_index"])
        baseline = proposal["baseline"]
        teacher = proposal["teacher"]
        lines = [
            "=" * 88,
            f"Teacher oracle trace: {proposal['problem_id']}",
            "Problem:",
            str(proposal["problem"]),
            f"Trusted reference answer: {proposal['reference_answer']}",
            "",
            "Baseline frozen answerer:",
            f"  output: {baseline['response'] or '(empty)'}",
            f"  final answer: {baseline['extracted_answer'] or '(empty)'}",
            f"  score: {float(baseline['score']):.0f}",
            f"  status: {baseline['generation_status'] or 'unknown'}",
            f"  latency/cost: {float(baseline['latency_s']):.2f}s / ${float(baseline['cost_usd']):.6f}",
            "",
            f"Teacher ({teacher['model']}):",
            f"  raw output: {teacher['raw_output'] or '(empty)'}",
            f"  accepted hints: {proposal['accepted_hints']}",
            f"  rejected hints: {proposal['rejected_hints']}",
            f"  latency/cost: {float(teacher['latency_s']):.2f}s / ${float(teacher['cost_usd']):.6f}",
        ]
        for candidate in candidates_by_call.get(call_index, []):
            hinted = candidate["hinted"]
            lines.extend(
                [
                    "",
                    f"Hinted frozen answerer candidate {candidate['candidate_index']}:",
                    f"  hint: {candidate['hint']}",
                    f"  leak check: {candidate['leak_check']}",
                    f"  output: {hinted['response'] or '(empty)'}",
                    f"  final answer: {hinted['extracted_answer'] or '(empty)'}",
                    f"  score: {float(hinted['score']):.0f}",
                    f"  training selection: {candidate['training_selection']}",
                    f"  latency/cost: {float(hinted['latency_s']):.2f}s / ${float(hinted['cost_usd']):.6f}",
                ]
            )
        sections.append("\n".join(lines))
    path.write_text("\n\n".join(sections) + ("\n" if sections else ""), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=1, help="Maximum dataset problems; defaults to one.")
    parser.add_argument("--candidates", type=int, default=1, help="Teacher hints per eligible problem.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--min-difficulty", type=float)
    parser.add_argument("--max-difficulty", type=float)
    parser.add_argument("--dataset-path", type=Path)
    parser.add_argument("--dataset-url", default=OMNI_MATH_RULE_URL)
    parser.add_argument(
        "--problem-ids",
        help="Comma-separated exact dataset IDs. Bypasses random/limit selection after loading.",
    )
    parser.add_argument("--baseline-predictions", type=Path)
    parser.add_argument(
        "--cached-hints-from",
        type=Path,
        help="Reuse accepted hints from a teacher_proposals.jsonl artifact without calling a teacher.",
    )
    parser.add_argument(
        "--target-current-failures",
        type=int,
        help="Freshly score up to --max-baseline-search items, then replay hints on exactly this many current Luna failures.",
    )
    parser.add_argument(
        "--max-baseline-search",
        type=int,
        default=20,
        help="Hard cap for the fresh baseline search used with --target-current-failures.",
    )
    parser.add_argument(
        "--teacher-on-all",
        action="store_true",
        help="Propose hints for baseline-correct items too; default only targets baseline misses.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("runs/teacher_hints"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--luna-model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", default="none")
    parser.add_argument("--think-mode", choices=THINK_MODE_CHOICES)
    parser.add_argument("--show-work", action="store_true")
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--teacher-model", default=DEFAULT_TEACHER_MODEL)
    parser.add_argument(
        "--hint-model",
        choices=("api", LFM2_HINT_MODEL_ALIAS),
        default="api",
        help="Hint provider: API teacher or the local LFM2 Math model.",
    )
    parser.add_argument(
        "--local-hint-device",
        choices=("auto", "cpu", "cuda", "mps"),
        default="auto",
        help="Runtime device for --hint-model lfm2-350m-math.",
    )
    parser.add_argument("--teacher-max-output-tokens", type=int, default=128)
    parser.add_argument("--teacher-reasoning-effort", choices=THINK_MODE_CHOICES, default="none")
    parser.add_argument(
        "--answer-aware-teacher",
        action="store_true",
        help="Give the teacher the trusted verifier answer for private checking only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1 or args.candidates < 1 or args.max_baseline_search < 1:
        raise ValueError("--limit, --candidates, and --max-baseline-search must be at least 1")
    if args.target_current_failures is not None and args.target_current_failures < 1:
        raise ValueError("--target-current-failures must be at least 1")
    if args.target_current_failures is not None and args.max_baseline_search > 20:
        raise ValueError("--max-baseline-search cannot exceed 20 for a current-failure comparison")
    if args.target_current_failures is not None and args.baseline_predictions:
        raise ValueError("--target-current-failures requires a fresh baseline; omit --baseline-predictions")
    if args.cached_hints_from and args.target_current_failures is not None:
        raise ValueError("--cached-hints-from cannot be combined with --target-current-failures")
    if args.hint_model != "api" and args.answer_aware_teacher:
        raise ValueError(
            "The local LFM2 hint provider is deployment-valid only and cannot receive a trusted answer. "
            "Remove --answer-aware-teacher or use --hint-model api."
        )
    problems = load_omni_math_rule(
        dataset_path=args.dataset_path,
        dataset_url=args.dataset_url,
        limit=None if args.problem_ids else (
            args.max_baseline_search if args.target_current_failures is not None else args.limit
        ),
        seed=args.seed,
        shuffle=args.shuffle,
        min_difficulty=args.min_difficulty,
        max_difficulty=args.max_difficulty,
    )
    if args.problem_ids:
        requested_ids = [item.strip() for item in args.problem_ids.split(",") if item.strip()]
        by_id = {problem.id: problem for problem in problems}
        missing = [item for item in requested_ids if item not in by_id]
        if missing:
            raise ValueError(f"requested dataset IDs not found: {', '.join(missing)}")
        problems = [by_id[item] for item in requested_ids]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir / run_id
    backend = LunaBackend(
        LunaConfig(
            model=args.luna_model,
            reasoning_effort=resolve_reasoning_effort(args.reasoning_effort, args.think_mode),
            max_output_tokens=args.max_output_tokens,
            show_work=args.show_work,
        ),
        dry_run=args.dry_run,
    )
    cached_provenance: list[dict[str, object]] | None = None
    if args.cached_hints_from:
        teacher, cached_provenance = load_cached_hint_teacher(args.cached_hints_from, problems, args.candidates)
    elif args.hint_model == "api":
        teacher: TeacherProtocol = TeacherHintGenerator(
            TeacherConfig(
                model=args.teacher_model,
                max_output_tokens=args.teacher_max_output_tokens,
                reasoning_effort=args.teacher_reasoning_effort,
                answer_aware=args.answer_aware_teacher,
            ),
            dry_run=args.dry_run,
        )
    elif args.dry_run:
        teacher = TeacherHintGenerator(
            TeacherConfig(model=LFM2_HINT_MODEL_ALIAS, answer_aware=False), dry_run=True
        )
    else:
        teacher = LocalHintGenerator(args.hint_model, device=args.local_hint_device)
    supplied = load_baseline_items(args.baseline_predictions, problems) if args.baseline_predictions else None
    summary = generate_teacher_data(
        problems=problems,
        backend=backend,
        teacher=teacher,
        output_dir=output_dir,
        candidates=args.candidates,
        teacher_on_all=args.teacher_on_all,
        supplied_baselines=supplied,
        target_baseline_failures=args.target_current_failures,
    )
    config_path = output_dir / "run_config.json"
    config_path.write_text(json.dumps(vars(args), default=str, indent=2), encoding="utf-8")
    summary["paths"]["run_config"] = str(config_path)
    if cached_provenance is not None:
        provenance_path = output_dir / "cached_hint_provenance.json"
        provenance_path.write_text(
            json.dumps(
                {
                    "source_artifact": str(args.cached_hints_from),
                    "items": cached_provenance,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        summary["cached_hint_source"] = str(args.cached_hints_from)
        summary["cached_hint_identity_verified"] = all(
            bool(item["identical"]) for item in cached_provenance
        )
        summary["paths"]["cached_hint_provenance"] = str(provenance_path)
    summary["answer_aware_teacher"] = args.answer_aware_teacher
    summary["experiment_label"] = (
        "answer-aware oracle upper bound; not deployment-valid"
        if args.answer_aware_teacher
        else "deployment-valid answer-blind teacher hints"
    )
    (output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote teacher-hint artifacts to {output_dir}")
    print(summary)


if __name__ == "__main__":
    main()
