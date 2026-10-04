"""Shared daily backtest engine: identical accounting for all models.

Daily order:
1. liquidate delisted positions to cash at last available price, costed;
2. mark risky positions to close; accrue the ^IRX-derived daily return on cash;
3. quarter boundary: members exiting the top-50 are force-sold to cash at
   close, costed; entrants receive weight at the next rebalance;
4. rebalance date (per-model config; benchmarks monthly, RL daily): model
   returns target weights over current members (sum = 1, long-only); cost =
   fees_bps/1e4 * sum(|w_target - w_drift|) over risky assets + cash.

Weights drift with prices between rebalances. Any exit (rank drop, delisting)
is a forced liquidation to cash at last available price; cash is engine-only.
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
