"""Hand-rolled PPO training loop (CleanRL reference). See docs/methodology.md."""

import logging
from typing import Any

log = logging.getLogger(__name__)


def train(cfg: dict[str, Any], args: Any) -> None:
    """Train the RL policy on the train split (PLAN.md Phase 3).

    Reads: train split (`split.train_out`), env params (`config/eval.yaml`)
    Writes: checkpoint artifact to the shared MLflow experiment
    """
    log.warning("RL training not yet implemented (PLAN.md Phase 3)")
