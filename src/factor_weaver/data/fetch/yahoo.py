"""Yahoo Finance source: extra index/ETF series and fallback prices for LSEG gaps.

Each symbol is cached as one parquet file under <yahoo.prices_out> (file
existence means cached; `--refresh` or deleting the file refetches). The build
step turns fallback rows into universe prices and splits the extra series into
<yahoo.extra_prices_out>.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from factor_weaver.data import store

log = logging.getLogger(__name__)

OUT_COLS = ["date", "symbol", "open", "high", "low", "close", "volume"]
_RENAME = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}


def resolve_symbol(cfg: dict[str, Any], ric: str, ticker: str) -> str:
    """Yahoo symbol for a universe RIC; <yahoo.symbol_overrides> wins over ticker."""
    return ((cfg.get("yahoo") or {}).get("symbol_overrides") or {}).get(ric, ticker)


def _normalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Rename a yfinance history frame to canonical (date, symbol, open..volume)."""
    df = df.rename(columns=_RENAME).reindex(columns=list(_RENAME.values()))
    df = df.rename_axis("date").reset_index()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if isinstance(df["date"].dtype, pd.DatetimeTZDtype):
        df["date"] = df["date"].dt.tz_localize(None)
    df["symbol"] = symbol
    df = df.dropna(subset=["date", "close"])
    return df.loc[:, OUT_COLS].sort_values(by="date").reset_index(drop=True)


def _fetch_symbol(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch one symbol; returns an empty canonical frame (not an error) on failure."""
    end_exclusive = f"{pd.Timestamp(end) + pd.Timedelta(days=1):%Y-%m-%d}"  # exclusive
    try:
        raw = yf.Ticker(symbol).history(
            start=str(start),
            end=end_exclusive,
            interval="1d",
            auto_adjust=True,  # split+dividend adjusted, closest to LSEG RTS
            actions=False,
        )
    except Exception as e:  # yfinance raises on network/parse problems
        log.warning("%s: yahoo error (%s)", symbol, str(e).splitlines()[0])
        return pd.DataFrame(columns=pd.Index(OUT_COLS))
    if raw.empty:
        log.warning("%s: no yahoo data", symbol)
        return pd.DataFrame(columns=pd.Index(OUT_COLS))
    return _normalize(raw, symbol)


def fetch_symbols(
    cfg: dict[str, Any], symbols: list[str], start: str, end: str, *, refresh: bool = False
) -> pd.DataFrame:
    """Fetch/cache every requested symbol; returns one long frame of what exists.

    Symbols already cached under <yahoo.prices_out> are skipped unless refresh.
    """
    cache_dir = Path(cfg["yahoo"]["prices_out"])
    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    cached = 0
    for symbol in symbols:
        path = store.cache_path(cache_dir, symbol)
        if path.exists() and not refresh:
            try:
                frames.append(pd.read_parquet(path))
                cached += 1
                log.debug("  %s: cached", symbol)
                continue
            except Exception as e:  # refetch a corrupt cache file
                log.warning("%s: cache unreadable (%s); refetching", symbol, e)
        missing.append(symbol)
    for symbol in missing:
        df = _fetch_symbol(symbol, start, end)
        if df.empty:
            continue
        store.write_parquet(df, store.cache_path(cache_dir, symbol))
        frames.append(df)
        log.debug("  %s: fetched %d rows", symbol, len(df))
    if symbols:
        log.info("yahoo: %d cached, %d fetched", cached, len(missing))
    if not frames:
        return pd.DataFrame(columns=pd.Index(OUT_COLS))
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(by=["date", "symbol"])
        .reset_index(drop=True)
    )
