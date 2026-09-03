"""CLI for the Omni-MATH rule prompt-policy MVP."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from .backend import THINK_MODE_CHOICES, LunaBackend, LunaConfig, resolve_reasoning_effort
from .controller import ControllerModelConfig, SMALLEST_CONTROLLER_MODEL, TinyController
from .datasets import OMNI_MATH_RULE_URL, load_omni_math_rule
from .evaluation import evaluate_problems


def main() -> None:
    args = parse_args()
    problems = load_omni_math_rule(
        dataset_path=args.dataset_path,
        dataset_url=args.dataset_url,
        limit=args.limit,
        seed=args.seed,
        shuffle=args.shuffle,
        min_difficulty=args.min_difficulty,
        max_difficulty=args.max_difficulty,
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir / run_id

    backend = LunaBackend(
        LunaConfig(
            model=args.luna_model,
            reasoning_effort=resolve_reasoning_effort(args.reasoning_effort, args.think_mode),
            max_output_tokens=args.max_output_tokens,
            temperature=args.luna_temperature,
            show_work=args.show_work,
        ),
        dry_run=args.dry_run,
    )
    controller = None
    if args.mode in {"controlled", "both"}:
        controller = TinyController(
            ControllerModelConfig(
                model=args.controller_model,
                max_new_tokens=args.controller_tokens,
                temperature=args.controller_temperature,
                top_p=args.controller_top_p,
                device=args.controller_device,
            ),
            dry_run=args.dry_run,
        )

    summary = evaluate_problems(
        problems=problems,
        backend=backend,
        controller=controller,
        output_dir=output_dir,
        mode=args.mode,
        controller_samples=args.controller_samples,
    )
    print(f"Wrote run artifacts to {output_dir}")
    print(summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--min-difficulty", type=float)
    parser.add_argument("--max-difficulty", type=float)
    parser.add_argument("--dataset-path", type=Path)
    parser.add_argument("--dataset-url", default=OMNI_MATH_RULE_URL)
    parser.add_argument("--output-dir", type=Path, default=Path("runs/omni_math_rule"))
    parser.add_argument("--mode", choices=["baseline", "controlled", "both"], default="both")
    parser.add_argument("--dry-run", action="store_true")

    parser.add_argument("--luna-model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", default="none")
    parser.add_argument(
        "--think-mode",
        choices=THINK_MODE_CHOICES,
        help="Native Luna reasoning effort. Overrides --reasoning-effort when supplied.",
    )
    parser.add_argument(
        "--show-work",
        action="store_true",
        help="Ask Luna for a concise derivation before the boxed final answer.",
    )
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--luna-temperature", type=float)

    parser.add_argument("--controller-model", default=SMALLEST_CONTROLLER_MODEL)
    parser.add_argument("--controller-samples", type=int, default=1)
    parser.add_argument("--controller-tokens", type=int, default=30)
    parser.add_argument("--controller-temperature", type=float, default=0.7)
    parser.add_argument("--controller-top-p", type=float, default=0.9)
    parser.add_argument("--controller-device", default="auto")
    return parser.parse_args()


if __name__ == "__main__":
    main()
