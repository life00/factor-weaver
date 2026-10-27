"""Daily technical features from adjusted OHLCV and split-adjusted shares."""

import logging
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from factor_weaver.data import store
from factor_weaver.data.build.fundamental import (
    asof_by_ric,
    latest_rows,
    quarterly_panel,
)

log = logging.getLogger(__name__)

TECHNICAL_FEATURES = [
    "momentum",
    "volatility",
    "size",
    "short_term_reversal",
    "share_turnover",
]


def build_technical(cfg: dict[str, Any]) -> None:
    """Compute <technical.out> as daily rows.

    Reads <prices.out>, <universe.assets_out>, <lseg.market_cap_out>,
    <lseg.fundamentals_out>.
    """
    prices_path = Path(cfg["prices"]["out"])
    if not prices_path.exists():
        raise FileNotFoundError(f"run the prices step first; missing: {prices_path}")
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    cap_path = Path(cfg["lseg"]["market_cap_out"])
    if not cap_path.exists():
        raise FileNotFoundError(f"run the lseg-market-cap step first; missing: {cap_path}")

    prices = pd.read_parquet(prices_path, columns=["date", "ric", "close", "volume"])
    prices["ric"] = prices["ric"].astype(str)
    prices["close"] = prices["close"].astype("float64")
    prices["volume"] = prices["volume"].astype("float64")
    assets = pd.read_parquet(assets_path, columns=["ric", "permid"])
    assets["ric"] = assets["ric"].astype(str)
    assets["permid"] = assets["permid"].astype(str)
    caps = pd.read_parquet(cap_path, columns=["date", "ric", "market_cap"])
    caps["ric"] = caps["ric"].astype(str)
    caps["market_cap"] = caps["market_cap"].astype("float64")
    caps = caps.rename(columns={"date": "cap_date"})

    shares = latest_rows(quarterly_panel(cfg)).loc[:, ["ric", "date", "shares"]]
    shares = shares.dropna(subset=["shares"])
    shares = shares.loc[shares["shares"] > 0]
    shares_by_ric = dict(tuple(shares.groupby("ric", sort=False)))
    caps_by_ric = dict(tuple(caps.groupby("ric", sort=False)))

    frames: list[pd.DataFrame] = []
    for ric, group in prices.groupby("ric", sort=False):
        g = group.sort_values("date").reset_index(drop=True)
        shares_ric = shares_by_ric.get(ric)
        if shares_ric is None:
            g["shares"] = np.nan
        else:
            g = asof_by_ric(g, shares_ric, "date", "date")

        cap_ric = caps_by_ric.get(ric)
        if cap_ric is None:
            g["cap_date"] = pd.NaT
            g["market_cap"] = np.nan
            g["close_cap"] = np.nan
        else:
            g = asof_by_ric(g, cap_ric, "date", "cap_date")
            px = g.loc[:, ["ric", "date", "close"]].rename(
                columns={"date": "px_date", "close": "close_cap"}
            )
            g = asof_by_ric(g, px, "cap_date", "px_date").drop(columns="px_date")
        g = g.sort_values("date").reset_index(drop=True)

        returns = g["close"].pct_change(fill_method=None)
        g["momentum"] = g["close"].shift(21) / g["close"].shift(252) - 1
        g["volatility"] = returns.rolling(252, min_periods=252).std() * np.sqrt(21)
        g["short_term_reversal"] = g["close"] / g["close"].shift(21) - 1
        g["share_turnover"] = g["volume"].rolling(21, min_periods=21).sum() / g["shares"]

        cap_age = (g["date"] - g["cap_date"]).dt.days
        size_ok = (
            cap_age.between(0, 120)
            & (g["market_cap"] > 0)
            & (g["close"] > 0)
            & (g["close_cap"] > 0)
        )
        g["size"] = np.log(
            (g["market_cap"] * g["close"] / g["close_cap"]).where(size_ok)
        )
        for col in TECHNICAL_FEATURES:
            values = cast(pd.Series, pd.to_numeric(g[col], errors="coerce"))
            g[col] = values.astype("float64").replace([np.inf, -np.inf], np.nan)
        frames.append(g.loc[:, ["date", "ric", *TECHNICAL_FEATURES]])

    out = pd.concat(frames, ignore_index=True).merge(assets, on="ric", how="inner")
    out = out.loc[out[TECHNICAL_FEATURES].notna().any(axis=1)]
    out = out.loc[
        (out["date"] >= pd.Timestamp(cfg["universe"]["start"]))
        & (out["date"] < pd.Timestamp(cfg["universe"]["end"]))
    ]
    out = (
        out.loc[:, ["date", "ric", "permid", *TECHNICAL_FEATURES]]
        .sort_values(["date", "ric"])
        .reset_index(drop=True)
    )
    if out.empty:
        raise RuntimeError("no technical features computed")

    path = Path(cfg["technical"]["out"])
    store.write_parquet(out, path)
    log.info(
        "wrote %s (%d rows, %d rics, %s..%s)",
        path,
        len(out),
        out["ric"].nunique(),
        out["date"].min(),
        out["date"].max(),
    )
