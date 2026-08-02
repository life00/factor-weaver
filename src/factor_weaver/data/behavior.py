def load_behavior(cfg: dict) -> None:
    """Load pre-computed sentiment/attention parquet from sibling repo.

    Reads: data/raw/behavioral/*.parquet
    Writes: data/interim/behavior.parquet (columns: date, ticker,
            sentiment_score, attention_score)
    """
    ...
