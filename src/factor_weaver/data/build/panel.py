"""Member-day panel: align the feature builds on one calendar, then normalize them.

align → <align.out>: one row per (trading day, universe member), every member on every
trading day of its quarter, missing values kept as NaN.
- calendar: the <CALENDAR_SYMBOL> index dates, i.e. exchange trading days; stray
  weekend rows in the stock prices are dropped
- membership: the snapshot at quarter-end q (ranked on q's market cap) holds on the
  trading days after q up to and including the next quarter-end
- close, ret: adjusted close and its total return P_t / P_{t-1} - 1 over the previous
  trading day; NaN on member days without a price (delisting tails)
- technical, behavioral: values of day d (both known at the close of d)
- fundamental: the latest report from the trading day after its availability date (an
  after-close filing is first tradable the next day), NaN once older than
  <align.fundamental_max_age_days>

clean → <clean.out>: each feature ranked per date across that date's members and mapped
to [-1, 1] (ties averaged), missing → 0, the cross-sectional median
[gu-2020-empirical-asset-pricing-ml]. close and ret pass through untouched.
"""

import logging
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from factor_weaver.data import store
from factor_weaver.data.build.behavioral import FEATURES as BEHAVIORAL_FEATURES
from factor_weaver.data.build.fundamental import FUNDAMENTAL_FEATURES
from factor_weaver.data.build.technical import TECHNICAL_FEATURES

log = logging.getLogger(__name__)

CALENDAR_SYMBOL = "^SP500TR"
FEATURES = [*TECHNICAL_FEATURES, *FUNDAMENTAL_FEATURES, *BEHAVIORAL_FEATURES]
COLS = ["date", "ric", "permid", "close", "ret", *FEATURES]


def _read(path: str, columns: list[str] | None = None) -> pd.DataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(f"run earlier data steps first; missing: {path}")
    df = pd.read_parquet(path, columns=columns)
    for col in ("ric", "permid"):
        if col in df:
            df[col] = df[col].astype(str)
    return df


def align_panel(cfg: dict[str, Any]) -> None:
    """Write <align.out> (columns: date, ric, permid, close, ret, *features).

    Reads: <universe.universe_out>, <prices.out>, <yahoo.extra_prices_out>,
           <technical.out>, <fundamental.out>, <marketpsych.out>
    """
    u = cfg["universe"]
    start, end = pd.Timestamp(u["start"]), pd.Timestamp(u["end"])
    extra = _read(cfg["yahoo"]["extra_prices_out"], ["date", "symbol"])
    cal = pd.DatetimeIndex(extra.loc[extra["symbol"] == CALENDAR_SYMBOL, "date"].unique())
    cal = cal[(cal >= start) & (cal < end)].sort_values()
    if cal.empty:
        raise RuntimeError(f"no {CALENDAR_SYMBOL} dates in [{start}, {end}); run extra-prices")

    universe = _read(u["universe_out"], ["quarter_end", "ric", "permid"])
    snapshots = pd.DataFrame({"quarter_end": np.sort(universe["quarter_end"].unique())})
    days = pd.merge_asof(
        pd.DataFrame({"date": cal}),
        snapshots,
        left_on="date",
        right_on="quarter_end",
        allow_exact_matches=False,
    ).dropna(subset=["quarter_end"])
    grid = days.merge(universe, on="quarter_end").drop(columns="quarter_end")

    px = _read(cfg["prices"]["out"], ["date", "ric", "close"])
    px["close"] = px["close"].astype("float64")
    px = px.loc[px["date"].isin(pd.Series(cal))].sort_values(["ric", "date"])
    px["ret"] = px.groupby("ric")["close"].pct_change(fill_method=None)
    tech = _read(cfg["technical"]["out"], ["date", "ric", *TECHNICAL_FEATURES])
    beh = _read(cfg["marketpsych"]["out"], ["date", "ric", *BEHAVIORAL_FEATURES])
    panel = grid
    for df in (px, tech, beh):
        panel = panel.merge(df, on=["date", "ric"], how="left")

    fund = _read(cfg["fundamental"]["out"], ["date", "ric", *FUNDAMENTAL_FEATURES])
    pos = cal.searchsorted(fund["date"].to_numpy(), side="right")
    fund = fund.loc[pos < len(cal)].rename(columns={"date": "avail"})
    fund["date"] = cal[pos[pos < len(cal)]].to_numpy()
    # filings on Friday and Saturday both enter on Monday: keep the later report
    fund = fund.sort_values("avail").drop_duplicates(["ric", "date"], keep="last")
    panel = pd.merge_asof(panel.sort_values("date"), fund.sort_values("date"), on="date", by="ric")
    stale = (panel["date"] - panel["avail"]).dt.days > cfg["align"]["fundamental_max_age_days"]
    panel.loc[stale, FUNDAMENTAL_FEATURES] = np.nan

    panel = panel.loc[:, COLS].sort_values(["date", "ric"]).reset_index(drop=True)
    if len(panel) != len(grid) or panel.duplicated(["date", "ric"]).any():
        raise ValueError("panel rows differ from the member-day grid; duplicate input keys?")
    path = Path(cfg["align"]["out"])
    store.write_parquet(panel, path)
    members = panel.groupby("date").size()
    log.info(
        "wrote %s (%d rows, %d days %s..%s, %d-%d members/day)",
        path,
        len(panel),
        len(members),
        panel["date"].min().date(),
        panel["date"].max().date(),
        members.min(),
        members.max(),
    )
    nan = panel[["close", "ret", *FEATURES]].isna().mean() * 100
    log.info("NaN %%: %s", ", ".join(f"{k} {v:.1f}" for k, v in nan.items()))


def clean_panel(cfg: dict[str, Any]) -> None:
    """Write <clean.out>: <align.out> with features ranked to [-1, 1] per date, NaN → 0.

    Reads: <align.out>
    """
    df = _read(cfg["align"]["out"])
    for f in FEATURES:
        by_date = df.groupby("date")[f]
        rank = cast(pd.Series, by_date.rank(method="average"))
        n = cast(pd.Series, by_date.transform("count"))
        df[f] = (rank - 1).div(n - 1).mul(2).sub(1).fillna(0.0)  # n == 1 → 0/0 → 0
    path = Path(cfg["clean"]["out"])
    store.write_parquet(df, path)
    log.info("wrote %s (%d rows, %d features ranked)", path, len(df), len(FEATURES))
