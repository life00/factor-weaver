def compute_technicals(cfg: dict) -> None:
    """Compute rolling technical indicators from daily OHLCV.

    Reads: data/processed/prices.parquet
    Writes: data/processed/technicals.parquet (columns: date, ticker, ma_20, ma_50, rsi_14, ...)
    """
    ...
