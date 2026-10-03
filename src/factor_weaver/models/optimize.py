"""Shared tangency optimizer: identical optimization across optimizer-based models."""

import pandas as pd


def tangency(mu: pd.Series, cov: pd.DataFrame, rf: float, cap: float) -> pd.Series:
    """Long-only max-Sharpe (tangency) weights with per-name weight cap.

    PyPortfolioOpt EfficientFrontier.max_sharpe; used unchanged by
    mean_variance, ml_forecast and black_litterman -> optimizer equivalence
    across the family (PLAN.md section 5.2).
    """
    ...
