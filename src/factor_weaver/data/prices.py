"""Assemble daily OHLCV for every distinct universe company.

Reads the company registry written by the universe step. LSEG is the primary
source; a RIC it has no data for is retried under `lseg.ric_fallbacks` and
finally sourced from Yahoo via the company ticker (`yahoo.symbol_overrides`
wins over the registry ticker), validated against the company's membership
window. The same Yahoo pass also fetches the configured `yahoo.extra_symbols`
(index/indicator series) into <yahoo.extra_prices_out>. Each RIC/symbol is
cached as one parquet file, so file existence means cached: delete the cache
dir to refetch (e.g. after changing the universe window). Failures are
reported but do not abort the run.

Reads: <universe.companies_out>
Writes: <prices.out> (columns: date, ric, open, high, low, close, volume),
        per-RIC cache under <lseg.prices_out>, <yahoo.extra_prices_out>
"""

from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd

from factor_weaver.data import yahoo
from factor_weaver.data.lseg import _session, fetch_history, resolve_ric

_OUT_COLS = ["date", "ric", "open", "high", "low", "close", "volume"]


def _cache_path(cache_dir: Path, ric: str) -> Path:
    """Collision-free cache filename for a RIC ('.SPX' -> '.SPX.parquet')."""
    return cache_dir / f"{quote(ric, safe='')}.parquet"


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


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


def _covers(df: pd.DataFrame, first: Any, last: Any) -> bool:
    """True when a fallback series spans the RIC's universe membership window."""
    return not df.empty and df["date"].min() <= first and df["date"].max() >= last


def fetch_prices(cfg: dict[str, Any]) -> None:
    """Fetch daily OHLCV for every company in the universe registry.

    1. LSEG per RIC (with lseg.ric_fallbacks), cached per RIC.
    2. One Yahoo pass for the tickers LSEG could not serve (validated against
       the company's membership window) plus the configured extra symbols.

    Reads: <universe.companies_out>
    Writes: <prices.out>, <yahoo.extra_prices_out>,
            per-RIC cache under <lseg.prices_out>
    """
    u, c, p = cfg["universe"], cfg["lseg"], cfg["prices"]
    registry_path = Path(u["companies_out"])
    if not registry_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {registry_path}")

    companies = pd.read_parquet(registry_path)
    cache_dir = Path(c["prices_out"])
    start, end = u["start"], u["end"]

    import lseg.data as ld

    ld.get_config().set_param("http.request-timeout", 300)  # default 20s too short for 30y

    frames: dict[str, pd.DataFrame] = {}
    pending: list[tuple[str, str, Any, Any, str]] = []
    fetched_lseg = 0
    with _session() as ld:
        for row in companies.to_dict("records"):
            ric = str(row["ric"])
            path = _cache_path(cache_dir, ric)
            if path.exists():
                try:
                    frames[ric] = pd.read_parquet(path)
                    continue
                except Exception as e:  # refetch a corrupt cache file
                    print(f"  {ric}: cache unreadable ({e}); refetching")
            fallback = resolve_ric(cfg, ric)
            df, err = _try_lseg(ld, ric, fallback if fallback != ric else None, start, end)
            if err is None:
                if len(df) >= 10000:
                    print(f"  {ric}: warning: hit the 10,000-row request ceiling")
                frames[ric] = df
                fetched_lseg += 1
                _atomic_write(df, path)
                print(f"  {ric}: fetched {len(df)} rows (lseg)")
            else:
                symbol = yahoo.resolve_symbol(cfg, ric, str(row["ticker"]))
                pending.append(
                    (ric, symbol, row["first_quarter_end"], row["last_quarter_end"], err)
                )

    extra_symbols = list((cfg.get("yahoo") or {}).get("extra_symbols") or [])
    symbols = list(dict.fromkeys([s for _, s, *_ in pending] + extra_symbols))
    raw = yahoo.fetch_symbols(cfg, symbols, start, end)

    failed: list[tuple[str, str]] = []
    fetched_yahoo = 0
    for ric, symbol, first, last, err in pending:
        df = raw.loc[raw["symbol"] == symbol].copy()
        if not _covers(df, first, last):
            failed.append((ric, f"{err}; yahoo {symbol}: no coverage"))
            print(f"  {ric}: FAILED ({err}; yahoo {symbol}: no coverage)")
            continue
        df["ric"] = ric
        frames[ric] = df.loc[:, _OUT_COLS]
        fetched_yahoo += 1
        print(f"  {ric}: fetched {len(df)} rows (yahoo:{symbol})")
    yahoo.write_extra_prices(cfg, raw)

    if not frames:
        raise RuntimeError(f"no price data fetched; failures: {failed}")
    out = Path(p["out"])
    df = pd.concat(frames.values(), ignore_index=True)
    df = df.loc[:, _OUT_COLS].sort_values(by=["date", "ric"])
    _atomic_write(df, out)
    cached = len(frames) - fetched_lseg - fetched_yahoo
    print(
        f"wrote {out} ({len(df)} rows, {len(frames)} rics:"
        f" {cached} cached, {fetched_lseg} lseg, {fetched_yahoo} yahoo, {len(failed)} failed)"
    )
    if failed:
        print(f"warning: {len(failed)} rics failed (rerun to retry):")
        for ric, err in failed:
            print(f"  {ric}: {err}")
