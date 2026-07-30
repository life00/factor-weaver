def align_dataset(cfg: dict) -> None:
    """Merge all features into a single long-tidy dataset.

    EDGAR-anchored forward-fill for fundamentals (no look-ahead),
    freshness counter for quarterly data,
    time-decay for behavioral features.

    Reads: data/processed/*.parquet (fundamentals, filing_dates, prices, technicals, behavior)
    Writes: data/processed/aligned.parquet (columns: date, ticker, *features)
    """
    ...
