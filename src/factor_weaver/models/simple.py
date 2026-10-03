"""Simple benchmarks: 1/N equal weighting and index buy-and-hold."""

import pandas as pd


def equal_weight(t: pd.Timestamp, members: list[str], hist: pd.DataFrame) -> dict[str, float]:
    """1/N over current universe members at each rebalance.

    Replicates the naive diversification baseline of DeMiguel et al. (2009);
    no factor inputs.
    """
    ...


def index_buy_hold(t: pd.Timestamp, members: list[str], hist: pd.DataFrame) -> dict[str, float]:
    """Buy ^GSPC once at window start (single cost event), never rebalance.

    Note: ^GSPC is a price index (no dividends).
    """
    ...
