"""Fetch price caches: LSEG primary per RIC, Yahoo fallback + extra series.

Writes only per-RIC/per-symbol parquet caches under <lseg.prices_out> and
<yahoo.prices_out>; the build step assembles the canonical interim files.
Cached files are never refetched unless the pipeline runs with --refresh.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from factor_weaver.data import store
from factor_weaver.data.fetch import yahoo
from factor_weaver.data.fetch.lseg import fetch_history, resolve_ric, session

log = logging.getLogger(__name__)

OUT_COLS = ["date", "ric", "open", "high", "low", "close", "volume"]


def _attempt(fn: Any) -> tuple[pd.DataFrame, str | None]:
    """Run a fetch callable; return (data, error), treating empty as an error."""
    try:
        df = fn()
    except Exception as e:  # vendors raise when nothing is found
        return pd.DataFrame(), str(e).splitlines()[0]
    if df.empty:
        return pd.DataFrame(), "no usable rows"
    return df, None


def _try_lseg(
    ld: Any, ric: str, fallback: str | None, start: str, end: str
) -> tuple[pd.DataFrame, str | None]:
    """Fetch ric from LSEG; on failure retry under fallback and relabel rows."""
    df, err = _attempt(lambda: fetch_history(ld, ric, start, end))
    if err is None:
        return df, None
    if fallback is None:
        return pd.DataFrame(), err
    df, fb_err = _attempt(lambda: fetch_history(ld, fallback, start, end))
    if fb_err is not None:
        return pd.DataFrame(), f"{err}; fallback {fallback}: {fb_err}"
    df["ric"] = ric
    return df, None


def _registry(cfg: dict[str, Any]) -> pd.DataFrame:
    """Asset registry written by the universe build step."""
    path = Path(cfg["universe"]["assets_out"])
    if not path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {path}")
    return pd.read_parquet(path)


def _is_refresh(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("_refresh"))


def fetch_lseg_prices(cfg: dict[str, Any]) -> None:
    """Cache daily OHLCV for every registry RIC from LSEG (ric_fallbacks applied).

    Reads: <universe.assets_out>
    Writes: per-RIC cache under <lseg.prices_out>
    """
    assets = _registry(cfg)
    cache_dir = Path(cfg["lseg"]["prices_out"])
    start, end = cfg["universe"]["start"], cfg["universe"]["end"]
    refresh = _is_refresh(cfg)

    pending: list[tuple[str, Path]] = []
    cached = 0
    for row in assets.to_dict("records"):
        ric = str(row["ric"])
        path = store.cache_path(cache_dir, ric, url_quote=True)
        if path.exists() and not refresh:
            cached += 1
            log.debug("  %s: cached", ric)
        else:
            pending.append((ric, path))

    fetched = 0
    failures: list[tuple[str, str]] = []
    if pending:  # no session/credentials needed when every RIC is cached
        import lseg.data as ld

        ld.get_config().set_param("http.request-timeout", 300)  # default 20s too short for 30y
        with session() as ld:
            for ric, path in pending:
                fallback = resolve_ric(cfg, ric)
                df, err = _try_lseg(ld, ric, fallback if fallback != ric else None, start, end)
                if err is None:
                    if len(df) >= 10000:
                        log.warning("%s: hit the 10,000-row request ceiling", ric)
                    store.write_parquet(df, path)
                    fetched += 1
                    log.debug("  %s: fetched %d rows", ric, len(df))
                else:
                    failures.append((ric, err))
                    log.debug("  %s: failed (%s)", ric, err)

    log.info(
        "lseg-prices: %d cached, %d fetched, %d failed (%d rics)",
        cached,
        fetched,
        len(failures),
        len(assets),
    )
    for ric, err in failures:
        log.warning("  %s: %s", ric, err)
    if cached + fetched == 0 and len(assets):
        raise RuntimeError(f"no LSEG price data fetched; failures: {failures}")


def fetch_yahoo_prices(cfg: dict[str, Any]) -> None:
    """Cache Yahoo series: fallback prices for RICs without LSEG data + extras.

    A RIC counts as covered when its LSEG cache exists; remaining RICs are
    fetched under their Yahoo symbol (validated against the membership window by
    the build step). Configured `extra_symbols` are always fetched.

    Reads: <universe.assets_out>
    Writes: per-symbol cache under <yahoo.prices_out>
    """
    assets = _registry(cfg)
    lseg_dir = Path(cfg["lseg"]["prices_out"])
    fallback = []
    for row in assets.to_dict("records"):
        ric = str(row["ric"])
        if store.cache_path(lseg_dir, ric, url_quote=True).exists():
            continue
        fallback.append(yahoo.resolve_symbol(cfg, ric, str(row["ticker"])))
    extras = list((cfg.get("yahoo") or {}).get("extra_symbols") or [])
    symbols = list(dict.fromkeys(fallback + extras))
    if not symbols:
        log.info("yahoo-prices: no fallback RICs or extra symbols")
        return
    log.info("yahoo-prices: %d fallback RICs, %d extra symbols", len(fallback), len(extras))
    yahoo.fetch_symbols(
        cfg, symbols, cfg["universe"]["start"], cfg["universe"]["end"], refresh=_is_refresh(cfg)
    )
