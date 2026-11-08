"""Daily behavioral features (docs/features.md #9, #10) from the MarketPsych slices.

A month's cached live-day slices and the monthly archive slice that supersedes them can
both be on disk; duplicates collapse to the archive row. Rows outside the configured
[marketpsych.start, end) window are dropped, because an archive covers its whole month
while start/end may be mid-month.

Per PermID on every calendar day d (MarketPsych publishes on weekends), with b = buzz
(0 on a day without a row) and s = sentiment (0 when buzz > 0 but no polar references):
- sentiment = Σ b·s / Σ b over the 7 days ending d [tetlock-2008-more-than-words,
  heston-2017-news-vs-sentiment]; NaN when that buzz is 0
- attention = log(1 + B_d) − log(1 + median(B_{d-7}, …, B_{d-56})), B_d = Σ b over the
  7 days ending d [da-2011-in-search-of-attention]
Full windows only. Both are NaN without any vendor row in the 63 days the attention
window reads: an unmapped or uncovered company, not zero attention. NaN = undefined;
the clean step fills it. The universe keeps one RIC per PermID per quarter; if a
company's RIC changes over time, its features are broadcast to each of its RICs.
"""

import logging
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from factor_weaver.data import store

log = logging.getLogger(__name__)

WEEK = 7  # days
WEEKS = 8  # prior weeks in the attention median
FEATURES = ["sentiment", "attention"]
OUT_COLS = ["date", "ric", "permid", *FEATURES]


def _features(g: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """One PermID's sparse rows → both features on every calendar day."""
    g = g.set_index("date").reindex(days)
    buzz = cast(pd.Series, g["buzz"])
    seen = buzz.notna()
    b = buzz.fillna(0.0)
    s = cast(pd.Series, g["sentiment"]).where(b > 0).fillna(0.0)
    week = cast(pd.Series, b.rolling(WEEK, min_periods=WEEK).sum())
    net = (b * s).rolling(WEEK, min_periods=WEEK).sum()
    prior = pd.concat([week.shift(WEEK * k) for k in range(1, WEEKS + 1)], axis=1)
    covered = seen.rolling(WEEK * (WEEKS + 1), min_periods=1).sum() > 0
    attention = np.log1p(week) - np.log1p(prior.median(axis=1, skipna=False))
    return pd.DataFrame(
        {
            "date": days,
            "sentiment": (net / week).where((week > 0) & covered),
            "attention": pd.Series(attention, index=days).where(covered),
        }
    )


def build_behavioral(cfg: dict[str, Any]) -> None:
    """Compute <marketpsych.out> as daily (date, ric) feature rows.

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
    start, end = pd.Timestamp(mp["start"]), pd.Timestamp(mp["end"])
    raw = raw[(raw["date"] >= start) & (raw["date"] < end)]
    days = pd.date_range(start, end, freq="D", inclusive="left")
    feats = pd.concat(
        [
            _features(cast(pd.DataFrame, g), days).assign(permid=permid)
            for permid, g in raw.groupby("permid", sort=False)
        ],
        ignore_index=True,
    )
    feats = feats.dropna(subset=FEATURES, how="all")
    out = (
        feats.merge(assets, on="permid", how="inner")
        .reindex(columns=OUT_COLS)
        .sort_values(["date", "ric"])
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
        log.warning("no behavioral features for %d rics: %s", len(missing), ", ".join(missing))
