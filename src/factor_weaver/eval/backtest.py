"""Shared daily backtest engine: identical accounting for all models.

At rebalance dates (per-model config, default monthly) the model produces
target weights over current universe members; cost = sum(|delta w|) *
fees_bps (10 bps/side default; Frazzini, Israel & Moskowitz median
implementation shortfall). Between rebalances weights drift with prices.
Quarter-boundary universe exits are forced sales to cash (costed);
delistings convert to cash at the last available price; cash yields the
^IRX-derived daily return.

Metrics: CAGR, annualized volatility, Sharpe, Sortino, max drawdown, Calmar,
average turnover. Outputs: equity curve, weights history, metrics.

Reads: data/interim/prices.parquet, data/interim/universe.parquet,
       data/interim/extra_prices.parquet (^IRX), panel file (Phase 2 models)
Writes: experiments/ (equity curve, weights history, metrics), MLflow run
See PLAN.md section 4.
"""

import pandas as pd


def run_backtest(
    model, prices: pd.DataFrame, universe: pd.DataFrame, rf: pd.Series, cfg: dict
) -> dict:
    """Run one weight-provider model through the shared engine."""
    ...
