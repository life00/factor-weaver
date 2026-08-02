"""Train the RL agent (not yet implemented)."""

from typing import Any


def run(cfg: dict[str, Any], args: Any) -> None:
    print("RL training not yet implemented")


def add_arguments(sub: Any) -> None:
    sub.add_parser("rl", help="RL training").set_defaults(func=run)
