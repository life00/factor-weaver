"""Assemble canonical interim price files from the raw LSEG/Yahoo caches.

For each universe RIC the LSEG cache wins; RICs without it fall back to their
Yahoo symbol, validated against the company's membership window. Configured
extra index/ETF series are written separately for the evaluation engine.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from factor_weaver.data import store

log = logging.getLogger(__name__)

PRICE_COLS = ["date", "ric", "open", "high", "low", "close", "volume"]
EXTRA_COLS = ["date", "symbol", "open", "high", "low", "close", "volume"]


def _covers(df: pd.DataFrame, first: Any, last: Any) -> bool:
    """True when a fallback series spans the RIC's universe membership window."""
    return not df.empty and df["date"].min() <= first and df["date"].max() >= last


def _read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:  # a corrupt cache should be visible, not silently skipped
        log.warning("%s: unreadable cache (%s)", path, e)
        return None


def _yahoo_symbol(cfg: dict[str, Any], ric: str, ticker: str) -> str:
    return ((cfg.get("yahoo") or {}).get("symbol_overrides") or {}).get(ric, ticker)


def build_prices(cfg: dict[str, Any]) -> None:
    """Merge raw caches into <prices.out> plus <yahoo.extra_prices_out>.

    Reads: <universe.companies_out>, <lseg.prices_out>, <yahoo.prices_out>
    Writes: <prices.out> (columns: date, ric, open..volume),
            <yahoo.extra_prices_out> (columns: date, symbol, open..volume)
    """
    registry_path = Path(cfg["universe"]["companies_out"])
    if not registry_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {registry_path}")
    companies = pd.read_parquet(registry_path)
    lseg_dir = Path(cfg["lseg"]["prices_out"])
    yahoo_dir = Path(cfg["yahoo"]["prices_out"])

    frames: dict[str, pd.DataFrame] = {}
    n_lseg = n_yahoo = 0
    missing: list[str] = []
    for row in companies.to_dict("records"):
        ric = str(row["ric"])
        df = _read_cache(store.cache_path(lseg_dir, ric, url_quote=True))
        if df is not None and not df.empty:
            n_lseg += 1
        else:
            symbol = _yahoo_symbol(cfg, ric, str(row["ticker"]))
            df = _read_cache(store.cache_path(yahoo_dir, symbol))
            if df is None or not _covers(df, row["first_quarter_end"], row["last_quarter_end"]):
                missing.append(ric)
                log.warning("%s: no price data (lseg or yahoo %s)", ric, symbol)
                continue
            n_yahoo += 1
        df["ric"] = ric
        frames[ric] = df.loc[:, PRICE_COLS]

    if not frames:
        raise RuntimeError("no price data assembled; run the fetch steps first")
    out = Path(cfg["prices"]["out"])
    prices = (
        pd.concat(frames.values(), ignore_index=True)
        .loc[:, PRICE_COLS]
        .sort_values(by=["date", "ric"])
    )
    store.write_parquet(prices, out)
    log.info(
        "wrote %s (%d rows, %d rics: %d lseg, %d yahoo, %d missing)",
        out,
        len(prices),
        len(frames),
        n_lseg,
        n_yahoo,
        len(missing),
    )
    if missing:
        log.warning("missing price data for %d rics: %s", len(missing), ", ".join(missing))
    _write_extra_prices(cfg, yahoo_dir)


def _write_extra_prices(cfg: dict[str, Any], yahoo_dir: Path) -> None:
    """Write the configured extra index/ETF series from the Yahoo caches."""
    y = cfg.get("yahoo") or {}
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
