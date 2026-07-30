def parse_fundamentals(cfg: dict) -> None:
    """Walk financialdatadb xlsx files, melt wide→long per ticker sheet.

    Reads: data/raw/financialdatadb/*.xlsx
    Writes: data/processed/fundamentals.parquet (columns: ticker, date, marketcap, ...)
    """
    ...
