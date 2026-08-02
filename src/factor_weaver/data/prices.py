def fetch_prices(cfg: dict) -> None:
    """Fetch daily OHLCV from Yahoo Finance for universe tickers.

    Reads: data/interim/universe.parquet
    Writes: data/interim/prices.parquet (columns: date, ticker, open, high, low, close, volume)
    """
    ...
