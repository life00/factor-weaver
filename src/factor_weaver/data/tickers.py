"""Shared ticker normalization: canonical US format, dot class delimiter."""

import pandas as pd


def normalize_ticker(v) -> str | None:
    """Canonical US ticker: uppercase, dot class delimiter (BRK-B -> BRK.B).

    Applies to every data source at ingestion (financialdatadb sheets, Yahoo
    Finance symbols, S&P500 list) so all interim tables join on one format.
    """
    if v is None or pd.isna(v):
        return None
    return str(v).strip().upper().replace("-", ".").replace("/", ".")
