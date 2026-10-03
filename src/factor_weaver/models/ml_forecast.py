"""ML benchmark: Gu, Kelly & Xiu (2020) GBRT forecasting + Ma et al. (2021) MV pipeline."""

import pandas as pd


def ml_forecast(t: pd.Timestamp, members: list[str], hist: pd.DataFrame) -> dict[str, float]:
    """Walk-forward GBRT return forecasts -> shared tangency().

    Monthly horizon, next-month excess-return target, GKX cross-sectional
    rank standardization, sklearn HistGradientBoostingRegressor with the GKX
    grid (leaves/shrinkage/trees, tuned on a temporal validation split),
    annual refit; predicted returns feed mean-variance per Ma et al. (2021).
    Training rows strictly < t (no look-ahead).
    """
    ...
