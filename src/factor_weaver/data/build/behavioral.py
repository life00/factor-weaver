"""Assemble the interim behavioral file from the MarketPsych fetch-written slices.

The universe keeps one RIC per PermID per quarter; if a company's RIC changes
over time, the PermID-keyed series is broadcast to each of its RICs.
Rows are sparse: a date without media coverage has no row here. A month's cached
live-day slices and the monthly archive slice that supersedes them can both be on
disk; duplicates collapse to the archive row. Rows outside the configured
[marketpsych.start, end) window are dropped, because an archive covers its whole
month while start/end may be mid-month.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from factor_weaver.data import store

log = logging.getLogger(__name__)

OUT_COLS = ["date", "ric", "permid", "source", "buzz", "sentiment"]


def build_behavioral(cfg: dict[str, Any]) -> None:
    """Merge the fetch-written slices into <marketpsych.out>, keyed by (date, ric, source).

    Reads: <universe.assets_out>, <marketpsych.raw_out>/*.parquet
    Writes: <marketpsych.out>
    """
    raw_dir = Path(cfg["marketpsych"]["raw_out"])
    caches = sorted(raw_dir.glob("*.parquet"))
    if not caches:
        raise FileNotFoundError(f"run the marketpsych fetch step first; missing: {raw_dir}")
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")

    assets = pd.read_parquet(assets_path, columns=["ric", "permid"])
    assets["permid"] = assets["permid"].astype(str)
    raw = pd.concat((pd.read_parquet(path) for path in caches), ignore_index=True)
    raw["permid"] = raw["permid"].astype(str)
    # shortcut: keeps the first of duplicate (permid,date,source); archive sorts before
    # live, a re-published day keeps the older slice
    raw = raw.drop_duplicates(subset=["permid", "date", "source"])
    mp = cfg["marketpsych"]
    raw = raw[(raw["date"] >= pd.Timestamp(mp["start"])) & (raw["date"] < pd.Timestamp(mp["end"]))]
    out = raw.merge(assets, on="permid", how="inner")
    out = (
        out.reindex(columns=OUT_COLS)
        .sort_values(["date", "ric", "source"])
        .reset_index(drop=True)
    )
    path = Path(cfg["marketpsych"]["out"])
    store.write_parquet(out, path)
    log.info(
        "wrote %s (%d rows, %d rics, %s..%s)",
        path,
        len(out),
        out["ric"].nunique(),
        out["date"].min(),
        out["date"].max(),
    )
    missing = sorted(set(assets["ric"]) - set(out["ric"]))
    if missing:
        log.warning("no marketpsych rows for %d rics: %s", len(missing), ", ".join(missing))
