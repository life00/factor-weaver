def compute_technicals(cfg: dict) -> None:
    """Compute rolling technical indicators from daily OHLCV.

    Reads: data/interim/prices.parquet
    Writes: data/interim/technicals.parquet (columns: date, ticker, ma_20, ma_50, rsi_14, ...)
    """
    ...
