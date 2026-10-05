"""Trained-policy adapter: exposes the RL policy to the shared engine."""

import pandas as pd


def policy(cfg: dict, t: pd.Timestamp, members: list[str], hist: pd.DataFrame) -> dict[str, float]:
    """Wrap the trained PPO policy (`cfg['rl']['checkpoint']`) as a
    weight-provider so eval/backtest.py treats the RL model identically to
    benchmarks (PLAN.md section 5.6). Implemented in Phase 3.
    """
    ...
