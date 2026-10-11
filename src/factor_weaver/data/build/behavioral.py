"""Assemble the interim behavioral file from the MarketPsych month caches.

PermID → RIC is one-to-many (GOOG.OQ/GOOGL.OQ, CMCSA.OQ/CMCSK.OQ^L15,
USB.N/FSR.N^B01), so each company series is broadcast to every RIC sharing it.
Rows are sparse: a date without media coverage has no row here.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from factor_weaver.data import store

log = logging.getLogger(__name__)

OUT_COLS = ["date", "ric", "permid", "source", "buzz", "sentiment"]


def build_behavioral(cfg: dict[str, Any]) -> None:
    """Merge the raw month caches into <marketpsych.out>, keyed by (date, ric, source).

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
