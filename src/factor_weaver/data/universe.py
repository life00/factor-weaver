def build_universe(cfg: dict) -> None:
    """Filter S&P500 tickers, rank by market cap per quarter, keep top N.

    Reads: data/interim/fundamentals.parquet
    Writes: data/interim/universe.parquet (columns: quarter_end, ticker, marketcap, rank)
    """
    ...
