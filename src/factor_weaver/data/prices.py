def fetch_prices(cfg: dict) -> None:
    """Fetch daily OHLCV from Yahoo Finance for universe tickers.

    Reads: data/processed/universe.parquet
    Writes: data/processed/prices.parquet (columns: date, ticker, open, high, low, close, volume)
    """
    ...
