"""Fundamental stock-quarter features with as-reported, no-lookahead dates.

A quarter's feature date is the latest availability date across its fields:
``max(source_date, original_announcement_date)``, or a 60-day fallback when both
are missing. Lagged inputs (TTM, asset growth, issuance) are used only if they
were already available at that date; otherwise the feature is NaN.
"""

import logging
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from factor_weaver.data import store

log = logging.getLogger(__name__)

FIELDS = {
    "TR.F.TotRevenue": "revenue",
    "TR.F.COGSTot": "cogs",
    "TR.F.SGATot": "sga",
    "TR.F.IntrExpn": "interest",
    "TR.F.ShHoldEqCom": "equity",
    "TR.F.TotAssets": "assets",
    "TR.F.ComShrOutsTot": "shares",
}
FUNDAMENTAL_FEATURES = [
    "net_share_issuance",
    "book_to_market",
    "operating_profitability",
    "asset_growth",
    "sales_to_price",
]


def quarterly_panel(cfg: dict[str, Any]) -> pd.DataFrame:
    """Wide quarterly fundamentals keyed by (ric, period_end) with a feature date.

    Reads <universe.assets_out> and every parquet under <lseg.fundamentals_out>.
    """
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    fund_dir = Path(cfg["lseg"]["fundamentals_out"])
    caches = sorted(fund_dir.glob("*.parquet"))
    if not caches:
        raise FileNotFoundError(f"run the lseg-fundamentals step first; missing: {fund_dir}")

    assets = pd.read_parquet(assets_path, columns=["ric", "permid"])
    assets["ric"] = assets["ric"].astype(str)
    assets["permid"] = assets["permid"].astype(str)
    raw = pd.concat((pd.read_parquet(path) for path in caches), ignore_index=True)
    raw["ric"] = raw["ric"].astype(str)

    periods: pd.DataFrame = raw.loc[:, ["ric", "period_end"]].drop_duplicates()
    periods = periods.sort_values(by="period_end", kind="stable")
    periods["next_period_end"] = periods.groupby("ric", sort=False)["period_end"].shift(-1)
    raw = raw.merge(periods, on=["ric", "period_end"], how="left")

    avail = raw[["source_date", "original_announcement_date"]].max(axis=1)
    fallback = raw["period_end"] + pd.Timedelta(60, unit="D")
    capped = raw["next_period_end"] - pd.Timedelta(1, unit="D")
    fallback = fallback.where(raw["next_period_end"].isna() | (fallback <= capped), capped)
    avail = avail.fillna(fallback).dt.normalize().clip(lower=raw["period_end"])
    dates = cast(
        pd.DataFrame,
        raw.assign(avail=avail)
        .groupby(["ric", "period_end"], as_index=False)
        .agg(date=("avail", "max")),
    )

    wide: pd.DataFrame = raw.pivot_table(
        index=["ric", "period_end"], columns="field", values="value", aggfunc="first"
    )
    wide = wide.rename(columns=FIELDS).reindex(columns=list(FIELDS.values())).reset_index()
    wide = wide.merge(dates, on=["ric", "period_end"], how="left")
    wide = wide.merge(assets, on="ric", how="inner")
    return wide.sort_values(["ric", "period_end"]).reset_index(drop=True)


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop stale announcements that would make a forward-filled panel go backwards."""
    df = df.sort_values(["ric", "date", "period_end"])
    df = df.drop_duplicates(["ric", "date"], keep="last")
    df = df.sort_values(["ric", "date", "period_end"])
    prev_max = df.groupby("ric", sort=False)["period_end"].transform(
        lambda periods: periods.cummax().shift()
    )
    keep = prev_max.isna() | (df["period_end"] > prev_max)
    return df.loc[keep].sort_values(["ric", "date"])


def _empty_like(series: pd.Series, index: pd.Index) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return pd.Series(pd.NaT, index=index, dtype=series.dtype)
    if pd.api.types.is_numeric_dtype(series.dtype):
        return pd.Series(np.nan, index=index, dtype="float64")
    return pd.Series(pd.NA, index=index, dtype=series.dtype)


def _asof_one(
    left: pd.DataFrame,
    right: pd.DataFrame | None,
    left_on: str,
    right_on: str,
    template: pd.DataFrame,
) -> pd.DataFrame:
    """One-RIC backward as-of merge; null left keys get null right values."""
    right_cols = [
        col
        for col in template.columns
        if col != "ric" and not (left_on == right_on and col == right_on)
    ]
    left = left.copy()
    left["_idx"] = range(len(left))
    right_df: pd.DataFrame = (
        cast(pd.DataFrame, template.iloc[0:0]) if right is None else right
    )
    if right_df.empty:
        for col in right_cols:
            left[col] = _empty_like(cast(pd.Series, template[col]), left.index)
        return left.sort_values(by="_idx").drop(columns="_idx").reset_index(drop=True)

    right_df = right_df.drop(columns="ric")
    right_df = right_df.loc[right_df[right_on].notna()].sort_values(by=right_on)
    if right_df.empty:
        for col in right_cols:
            left[col] = _empty_like(cast(pd.Series, template[col]), left.index)
        return left.sort_values(by="_idx").drop(columns="_idx").reset_index(drop=True)

    valid = cast(pd.Series, left[left_on].notna())
    frames: list[pd.DataFrame] = []
    if bool(valid.any()):
        left_valid = left.loc[valid].sort_values(by=left_on)
        if left_on == right_on:
            merged = pd.merge_asof(left_valid, right_df, on=left_on, direction="backward")
        else:
            merged = pd.merge_asof(
                left_valid, right_df, left_on=left_on, right_on=right_on, direction="backward"
            )
        frames.append(merged)
    if not bool(valid.all()):
        left_missing = left.loc[~valid].copy()
        for col in right_cols:
            left_missing[col] = _empty_like(cast(pd.Series, template[col]), left_missing.index)
        frames.append(left_missing)
    result = pd.concat(frames, ignore_index=True)
    return result.sort_values(by="_idx").drop(columns="_idx").reset_index(drop=True)


def asof_by_ric(
    left: pd.DataFrame, right: pd.DataFrame, left_on: str, right_on: str
) -> pd.DataFrame:
    """Backward as-of merge per RIC.

    pandas requires the on-key to be globally sorted even with ``by="ric"``;
    the RIC order here is not globally date-sorted, so merge one RIC at a time.
    """
    groups = dict(tuple(right.groupby("ric", sort=False)))
    parts = [
        _asof_one(part, groups.get(ric), left_on, right_on, right)
        for ric, part in left.groupby("ric", sort=False)
    ]
    return pd.concat(parts, ignore_index=True)


def _with_features(panel: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for _, group in panel.groupby("ric", sort=False):
        g = group.sort_values("period_end").copy()
        date_int = g["date"].astype("int64")

        span3 = (g["period_end"] - g["period_end"].shift(3)).dt.days
        avail3 = date_int.rolling(4, min_periods=4).max()
        ttm_ok = span3.between(240, 310) & (avail3 == date_int)
        revenue_ttm = cast(pd.Series, g["revenue"].rolling(4, min_periods=4).sum())
        cogs_ttm = cast(pd.Series, g["cogs"].fillna(0).rolling(4, min_periods=4).sum())
        sga_ttm = cast(pd.Series, g["sga"].fillna(0).rolling(4, min_periods=4).sum())
        interest_ttm = cast(
            pd.Series, g["interest"].fillna(0).rolling(4, min_periods=4).sum()
        )
        profit_ttm = revenue_ttm - cogs_ttm - sga_ttm - interest_ttm

        span4 = (g["period_end"] - g["period_end"].shift(4)).dt.days
        asset_ok = (
            span4.between(330, 400)
            & (g["date"] >= g["date"].shift(4))
            & (g["assets"].shift(4) > 0)
        )

        span12 = (g["period_end"] - g["period_end"].shift(12)).dt.days
        shares_ratio = cast(pd.Series, g["shares"] / g["shares"].shift(12))
        issuance_ok = (
            span12.between(1000, 1200)
            & (g["date"] >= g["date"].shift(12))
            & (g["shares"] > 0)
            & (g["shares"].shift(12) > 0)
        )

        g["net_share_issuance"] = np.log(shares_ratio.where(issuance_ok))
        g["book_to_market"] = (g["equity"] / g["me"]).where(
            (g["equity"] > 0) & (g["me"] > 0)
        )
        g["operating_profitability"] = (profit_ttm / g["equity"]).where(
            (g["equity"] > 0) & ttm_ok
        )
        g["asset_growth"] = (g["assets"] / g["assets"].shift(4) - 1).where(asset_ok)
        g["sales_to_price"] = (revenue_ttm / g["me"]).where(ttm_ok & (g["me"] > 0))
        for col in FUNDAMENTAL_FEATURES:
            values = cast(pd.Series, pd.to_numeric(g[col], errors="coerce"))
            g[col] = values.astype("float64").replace([np.inf, -np.inf], np.nan)
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def build_fundamental(cfg: dict[str, Any]) -> None:
    """Compute <fundamental.out> as quarterly event rows without lookahead.

    Reads <prices.out>, <lseg.market_cap_out>, <universe.assets_out>,
    <lseg.fundamentals_out>.
    """
    prices_path = Path(cfg["prices"]["out"])
    if not prices_path.exists():
        raise FileNotFoundError(f"run the prices step first; missing: {prices_path}")
    cap_path = Path(cfg["lseg"]["market_cap_out"])
    if not cap_path.exists():
        raise FileNotFoundError(f"run the lseg-market-cap step first; missing: {cap_path}")

    prices = pd.read_parquet(prices_path, columns=["date", "ric", "close"])
    prices["ric"] = prices["ric"].astype(str)
    prices["close"] = prices["close"].astype("float64")
    caps = pd.read_parquet(cap_path, columns=["date", "ric", "market_cap"])
    caps["ric"] = caps["ric"].astype(str)
    caps["market_cap"] = caps["market_cap"].astype("float64")

    q = quarterly_panel(cfg)
    q = asof_by_ric(q, caps.rename(columns={"date": "cap_date"}), "date", "cap_date")
    q = asof_by_ric(
        q,
        prices.rename(columns={"date": "px_date", "close": "close_cap"}),
        "cap_date",
        "px_date",
    )
    q = asof_by_ric(q, prices.rename(columns={"close": "close_t"}), "date", "date")

    cap_age = (q["date"] - q["cap_date"]).dt.days
    me_ok = (
        cap_age.between(0, 120)
        & (q["market_cap"] > 0)
        & (q["close_t"] > 0)
        & (q["close_cap"] > 0)
    )
    q["me"] = (q["market_cap"] * q["close_t"] / q["close_cap"]).where(me_ok)

    rows = _with_features(q)
    rows = rows.loc[rows[FUNDAMENTAL_FEATURES].notna().any(axis=1)]
    rows = latest_rows(rows)
    cols = ["date", "ric", "permid", *FUNDAMENTAL_FEATURES]
    out = rows.loc[:, cols].copy()
    out = out.loc[
        (out["date"] >= pd.Timestamp(cfg["universe"]["start"]))
        & (out["date"] < pd.Timestamp(cfg["universe"]["end"]))
    ]
    out = out.sort_values(["date", "ric"]).reset_index(drop=True)
    if out.empty:
        raise RuntimeError("no fundamental features computed")

    path = Path(cfg["fundamental"]["out"])
    store.write_parquet(out, path)
    log.info(
        "wrote %s (%d rows, %d rics, %s..%s)",
        path,
        len(out),
        out["ric"].nunique(),
        out["date"].min(),
        out["date"].max(),
    )
