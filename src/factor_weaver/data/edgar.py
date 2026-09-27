def fetch_filing_dates(cfg: dict) -> None:
    """Query SEC EDGAR submissions API for 10-Q filing dates per (ticker, quarter).

    Reads: data/interim/companies.parquet
    Writes: data/interim/filing_dates.parquet (columns: ticker, quarter_end, filing_date)
    """
    ...
