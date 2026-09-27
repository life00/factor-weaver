"""Yahoo Finance source: fallback prices for LSEG gaps and extra index series.

Universe fallback tickers and the configured `extra_symbols` are fetched in one
pass, each symbol cached as one parquet file under <yahoo.prices_out> (file
existence means cached: delete the dir to refetch, e.g. after changing the
universe window). The caller turns fallback rows into universe prices; the
extra index/indicator series go to <yahoo.extra_prices_out>.

Reads: <yahoo.extra_symbols>, <universe.start/end> (fallback tickers from caller)
Writes: <yahoo.prices_out>/<symbol>.parquet, <yahoo.extra_prices_out>
"""

from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

_OUT_COLS = ["date", "symbol", "open", "high", "low", "close", "volume"]
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
    return df.loc[:, _OUT_COLS].sort_values(by="date").reset_index(drop=True)


def _fetch_symbol(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch one symbol; returns an empty canonical frame (not an error) on failure."""
    end_exclusive = (
        f"{pd.Timestamp(end) + pd.Timedelta(days=1):%Y-%m-%d}"  # yfinance end is exclusive
    )
    try:
        raw = yf.Ticker(symbol).history(
            start=str(start),
            end=end_exclusive,
            interval="1d",
            auto_adjust=True,  # split+dividend adjusted, closest to LSEG RTS
            actions=False,
        )
    except Exception as e:  # yfinance raises on network/parse problems
        print(f"  {symbol}: yahoo error ({str(e).splitlines()[0]})")
        return pd.DataFrame(columns=pd.Index(_OUT_COLS))
    if raw.empty:
        print(f"  {symbol}: no yahoo data")
        return pd.DataFrame(columns=pd.Index(_OUT_COLS))
    return _normalize(raw, symbol)


def _cache_path(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"{symbol}.parquet"


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def fetch_symbols(cfg: dict[str, Any], symbols: list[str], start: str, end: str) -> pd.DataFrame:
    """Fetch/cache every requested symbol; returns one long frame of what exists."""
    cache_dir = Path(cfg["yahoo"]["prices_out"])
    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    for symbol in symbols:
        path = _cache_path(cache_dir, symbol)
        if path.exists():
            try:
                frames.append(pd.read_parquet(path))
                continue
            except Exception as e:  # refetch a corrupt cache file
                print(f"  {symbol}: cache unreadable ({e}); refetching")
        missing.append(symbol)
    for symbol in missing:
        df = _fetch_symbol(symbol, start, end)
        if df.empty:
            continue
        _write(df, _cache_path(cache_dir, symbol))
        frames.append(df)
    if symbols:
        print(f"  yahoo: {len(symbols) - len(missing)} cached, {len(missing)} fetched")
    if not frames:
        return pd.DataFrame(columns=pd.Index(_OUT_COLS))
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(by=["date", "symbol"])
        .reset_index(drop=True)
    )


def write_extra_prices(cfg: dict[str, Any], raw: pd.DataFrame) -> None:
    """Write the configured extra index/indicator series to <yahoo.extra_prices_out>."""
    y = cfg["yahoo"]
    symbols = list(y.get("extra_symbols") or [])
    if not symbols:
        return
    df = raw.loc[raw["symbol"].isin(symbols), _OUT_COLS].copy()
    out = Path(y["extra_prices_out"])
    _write(df, out)
    missing = [s for s in symbols if s not in set(df["symbol"])]
    print(f"wrote {out} ({len(df)} rows, {df['symbol'].nunique()} extra symbols)")
    if missing:
        print(f"warning: no yahoo data for extra symbols: {', '.join(missing)}")
