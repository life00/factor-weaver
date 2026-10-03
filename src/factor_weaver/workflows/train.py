"""Train the RL model, models/rl (not yet implemented; PLAN.md Phase 3)."""

from typing import Any


def run(cfg: dict[str, Any], args: Any) -> None:
    print("RL training not yet implemented")


def add_arguments(sub: Any) -> None:
    sub.add_parser("rl", help="Train the RL model (models/rl)").set_defaults(func=run)
