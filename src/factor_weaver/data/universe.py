def build_universe(cfg: dict) -> None:
    """Filter S&P500 tickers, rank by market cap per quarter, keep top N.

    Reads: data/processed/fundamentals.parquet
    Writes: data/processed/universe.parquet (columns: quarter_end, ticker, marketcap, rank)
    """
    ...
