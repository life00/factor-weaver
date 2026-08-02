def split_dataset(cfg: dict) -> None:
    """Split aligned dataset into train/test by date window.

    Reads: data/interim/aligned.parquet
    Writes: data/train/*.parquet, data/test/*.parquet
    """
    ...
