"""Shared parquet persistence: atomic writes and cache paths."""

from pathlib import Path
from urllib.parse import quote

import pandas as pd


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write parquet atomically (tmp file + replace) so caches never go partial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def cache_path(cache_dir: Path, key: str, *, url_quote: bool = False) -> Path:
    """One parquet file per cache key; url_quote for keys with path separators (RICs)."""
    name = quote(key, safe="") if url_quote else key
    return cache_dir / f"{name}.parquet"
