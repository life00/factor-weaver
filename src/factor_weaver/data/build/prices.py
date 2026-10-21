"""Assemble canonical interim price files from the raw caches.

Universe stock prices come only from the per-RIC LSEG caches; the configured
extra index/ETF series (Yahoo) are written separately for the evaluation engine.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from factor_weaver.data import store

log = logging.getLogger(__name__)

PRICE_COLS = ["date", "ric", "open", "high", "low", "close", "volume"]
EXTRA_COLS = ["date", "symbol", "open", "high", "low", "close", "volume"]


def _read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:  # a corrupt cache should be visible, not silently skipped
        log.warning("%s: unreadable cache (%s)", path, e)
        return None


def build_prices(cfg: dict[str, Any]) -> None:
    """Merge the LSEG caches into <prices.out>.

    Reads: <universe.assets_out>, <lseg.prices_out>
    Writes: <prices.out> (columns: date, ric, open..volume)
    """
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    assets = pd.read_parquet(assets_path)
    lseg_dir = Path(cfg["lseg"]["prices_out"])

    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    for ric in assets["ric"].astype(str):
        df = _read_cache(store.cache_path(lseg_dir, ric, url_quote=True))
        if df is None or df.empty:
            missing.append(ric)
            continue
        frames.append(df.loc[:, PRICE_COLS])

    if not frames:
        raise RuntimeError("no price data assembled; run the lseg-prices step first")
    out = Path(cfg["prices"]["out"])
    prices = pd.concat(frames, ignore_index=True).sort_values(by=["date", "ric"])
    store.write_parquet(prices, out)
    log.info("wrote %s (%d rows, %d rics, %d missing)", out, len(prices), len(frames), len(missing))
    if missing:
        log.warning("missing price data for %d rics: %s", len(missing), ", ".join(missing))


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
