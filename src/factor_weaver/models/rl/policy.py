"""Trained-policy adapter: exposes the RL policy to the shared engine."""

import pandas as pd


def policy(model, t: pd.Timestamp, members: list[str], hist: pd.DataFrame) -> dict[str, float]:
    """Wrap a trained PPO policy as a weight-provider so eval/backtest.py
    treats the RL model identically to benchmarks (PLAN.md section 5.6).
    """
    ...
