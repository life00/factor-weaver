"""Assemble canonical interim price files from the raw caches.

Universe stock prices come only from the per-RIC LSEG caches (RTS-adjusted for splits and
spin-offs), back-adjusted here for cash dividends from the cached LSEG dividend records;
the configured extra index/ETF series (Yahoo) are written separately for the evaluation
engine.
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from factor_weaver.data import store

log = logging.getLogger(__name__)

PRICE_COLS = ["date", "ric", "open", "high", "low", "close", "volume"]
EXTRA_COLS = ["date", "symbol", "open", "high", "low", "close", "volume"]
_CASH_PAYMENTS = ["Cash Dividend", "Cash and Stock Alternative"]


def _dividend_adjust(df: pd.DataFrame, divs: pd.DataFrame | None) -> tuple[pd.DataFrame, int]:
    """Back-adjust OHLC for cash dividends from the LSEG dividend records.

    An ex-day's factor is U / (U + D), with U the unadjusted close and D the unadjusted gross
    dividend: the dividend is reinvested at the ex-date close, so the adjusted ex-day return
    is (P + D) / P_prev. Each day's prices take the product of all later factors. A dividend
    RTS already removed (some specials, e.g. COST 2012-12-06) is skipped: there the
    RTS/unadjusted ratio steps by about 1 - D / U_prev. Returns (frame, dividends applied).
    """
    if divs is None or divs.empty:
        return df, 0
    gross = divs["gross"].astype(float)
    keep = (
        divs["payment_type"].isin(_CASH_PAYMENTS).to_numpy(bool)
        & (divs["div_type"] != "Rescinded payment").to_numpy(bool)
        & (gross > 0).to_numpy(bool)
    )
    dates = df["date"].to_numpy("datetime64[ns]")
    pos = np.searchsorted(dates, divs["ex_date"].to_numpy("datetime64[ns]")[keep])
    amount = np.zeros(len(df))
    np.add.at(amount, pos[pos < len(df)], gross.to_numpy()[keep][pos < len(df)])

    u = df["close_unadj"].astype(float).to_numpy()
    k = df["close"].astype(float).to_numpy() / u  # RTS / unadjusted
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = amount / np.r_[np.nan, u[:-1]]
        step = np.r_[np.nan, k[:-1]] / k
        in_rts = (step < 1 - frac / 2) & (step > 1 - 2 * frac)
        apply = (amount > 0) & ~in_rts & np.isfinite(u)
        factor = np.where(apply, u / (u + amount), 1.0)
    if ((amount > 0) & ~np.isfinite(u)).any():
        log.debug("%s: dividends skipped, no unadjusted close", df["ric"].iloc[0])
    later = np.r_[np.cumprod(factor[::-1])[::-1][1:], 1.0]
    cols = ["open", "high", "low", "close"]
    df[cols] = df[cols].mul(later, axis=0)
    return df, int(apply.sum())


def _read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:  # a corrupt cache should be visible, not silently skipped
        log.warning("%s: unreadable cache (%s)", path, e)
        return None


def build_prices(cfg: dict[str, Any]) -> None:
    """Dividend-adjust the LSEG caches and merge them into <prices.out>.

    Reads: <universe.assets_out>, <lseg.prices_out>, <lseg.dividends_out>
    Writes: <prices.out> (columns: date, ric, open..volume)
    """
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    assets = pd.read_parquet(assets_path)
    lseg_dir = Path(cfg["lseg"]["prices_out"])
    div_dir = Path(cfg["lseg"]["dividends_out"])

    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    no_dividends: list[str] = []
    for ric in assets["ric"].astype(str):
        df = _read_cache(store.cache_path(lseg_dir, ric, url_quote=True))
        if df is None or df.empty:
            missing.append(ric)
            continue
        if "close_unadj" not in df:
            raise RuntimeError(f"{ric}: old price cache; run `data fetch lseg-prices --refresh`")
        divs = _read_cache(store.cache_path(div_dir, ric, url_quote=True))
        df, applied = _dividend_adjust(df.sort_values("date", ignore_index=True), divs)
        if not applied:
            no_dividends.append(ric)
        frames.append(df.loc[:, PRICE_COLS])

    if not frames:
        raise RuntimeError("no price data assembled; run the lseg-prices step first")
    out = Path(cfg["prices"]["out"])
    prices = pd.concat(frames, ignore_index=True).sort_values(by=["date", "ric"])
    store.write_parquet(prices, out)
    log.info("wrote %s (%d rows, %d rics, %d missing)", out, len(prices), len(frames), len(missing))
    if missing:
        log.warning("missing price data for %d rics: %s", len(missing), ", ".join(missing))
    if no_dividends:
        log.info(
            "no dividends applied for %d rics: %s", len(no_dividends), ", ".join(no_dividends)
        )


def build_extra_prices(cfg: dict[str, Any]) -> None:
    """Merge the configured extra series' Yahoo caches into <yahoo.extra_prices_out>.

    Reads: <yahoo.prices_out>
    Writes: <yahoo.extra_prices_out> (columns: date, symbol, open..volume)
    """
    y = cfg.get("yahoo") or {}
    yahoo_dir = Path(y["prices_out"])
    symbols = list(y.get("extra_symbols") or [])
    if not symbols:
        return
    frames = [
        df for s in symbols if (df := _read_cache(store.cache_path(yahoo_dir, s))) is not None
    ]
    df = (
        pd.concat(frames, ignore_index=True).loc[:, EXTRA_COLS].sort_values(by=["date", "symbol"])
        if frames
        else pd.DataFrame(columns=pd.Index(EXTRA_COLS))
    )
    out = Path(y["extra_prices_out"])
    store.write_parquet(df, out)
    log.info("wrote %s (%d rows, %d extra symbols)", out, len(df), df["symbol"].nunique())
    missing = [s for s in symbols if s not in set(df["symbol"])]
    if missing:
        log.warning("no yahoo data for extra symbols: %s", ", ".join(missing))
