"""Evaluate models through the shared backtest engine (PLAN.md section 6)."""

import logging
from typing import Any

log = logging.getLogger(__name__)


def run(cfg: dict[str, Any], args: Any) -> None:
    log.warning("evaluation not yet implemented (Phase 1, PLAN.md section 9)")


def add_arguments(sub: Any) -> None:
    sub.add_parser(
        "eval", help="Evaluate models (benchmarks, RL) via the shared engine"
    ).set_defaults(func=run, configs=("data", "eval", "models"))
