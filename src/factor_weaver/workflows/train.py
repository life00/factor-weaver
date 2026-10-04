"""Train the RL model, models/rl (not yet implemented; PLAN.md Phase 3)."""

import logging
from typing import Any

log = logging.getLogger(__name__)


def run(cfg: dict[str, Any], args: Any) -> None:
    log.warning("RL training not yet implemented")


def add_arguments(sub: Any) -> None:
    sub.add_parser("rl", help="Train the RL model (models/rl)").set_defaults(
        func=run, configs=("data", "models")
    )
