"""Evaluate a trained agent (not yet implemented)."""

from typing import Any


def run(cfg: dict[str, Any], args: Any) -> None:
    print("Evaluation not yet implemented")


def add_arguments(sub: Any) -> None:
    sub.add_parser("eval", help="Evaluate trained agent").set_defaults(func=run)
