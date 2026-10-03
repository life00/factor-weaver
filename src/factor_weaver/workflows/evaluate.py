"""Evaluate models through the shared backtest engine (PLAN.md section 6)."""

from typing import Any


def run(cfg: dict[str, Any], args: Any) -> None:
    print("Evaluation not yet implemented (Phase 1, PLAN.md section 9)")


def add_arguments(sub: Any) -> None:
    sub.add_parser(
        "eval", help="Evaluate models (benchmarks, RL) via the shared engine"
    ).set_defaults(func=run)
