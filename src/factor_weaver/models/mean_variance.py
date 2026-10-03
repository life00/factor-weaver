"""Mean-variance benchmark: Markowitz (1952) max-Sharpe tangency from historical stats."""

import pandas as pd


def mean_variance(t: pd.Timestamp, members: list[str], hist: pd.DataFrame) -> dict[str, float]:
    """Rolling lookback (config/models.yaml, default 5y daily) -> sample mean
    mu, Ledoit-Wolf covariance (sklearn) -> shared tangency().
    """
    ...
