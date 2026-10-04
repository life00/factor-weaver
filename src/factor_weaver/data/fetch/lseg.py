"""LSEG data API access: platform session (lseg-data library) + S&P500 constituents.

S&P500 membership history is reconstructed (in universe.py) from the current
constituent snapshot as anchor plus joiner/leaver events applied backwards.
"""

import logging
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from dotenv import load_dotenv

from factor_weaver.data import store

log = logging.getLogger(__name__)

_ENV_VARS = ("APP_KEY", "RDP_LOGIN", "RDP_PASSWORD")

# Field spelling as documented in LSEG's own articles (the "ituent" is theirs).
_JL_FIELDS = [
    "TR.IndexJLConstituentChangeDate",
    "TR.IndexJLConstituentRIC",
    "TR.IndexJLConstituentName",
    "TR.IndexJLConstituentituentChange",
]
_JL_TITLES = {
    "Date": "date",
    "Constituent RIC": "ric",
    "Constituent Name": "name",
    "Change": "change",
}

# Market cap probes (2026-08): TR.CompanyMarketCap is a genuine quarterly series
# (last trading day of quarter) but empty for retired RICs; TR.F.MktCap is annual
# fiscal period-ends forward-filled, used only as fallback for retired RICs.
_MC_FIELDS = ["TR.CompanyMarketCap.date", "TR.CompanyMarketCap"]
_MC_FALLBACK_FIELDS = ["TR.F.MktCap.date", "TR.F.MktCap"]
_MC_TITLES = {"Date": "date", "Company Market Cap": "market_cap"}
_MC_FALLBACK_TITLES = {"Date": "date", "Market Capitalization": "market_cap"}
_MC_CHUNK = 250  # ponytail: keeps each datagrid call well under the 300s server timeout


def _api_date(value: str | date) -> str:
    """Format a config/ISO date as the YYYYMMDD the LSEG API expects."""
    return f"{pd.Timestamp(value):%Y%m%d}"


def _credentials() -> dict[str, str]:
    """Read LSEG credentials from .env (loaded into os.environ if present)."""
    load_dotenv()
    values = {name: os.getenv(name) for name in _ENV_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"missing LSEG credentials in .env: {', '.join(missing)}")
    return {name: value for name, value in values.items() if value is not None}


@contextmanager
def session() -> Iterator[Any]:
    """Open a platform session (OAuth2 password grant); yields the lseg.data module."""
    import lseg.data as ld

    creds = _credentials()
    session = ld.session.platform.Definition(
        app_key=creds["APP_KEY"],
        grant=ld.session.platform.GrantPassword(
            username=creds["RDP_LOGIN"],
            password=creds["RDP_PASSWORD"],
        ),
        signon_control=True,
    ).get_session()
    ld.session.set_default(session)
    session.open()
    try:
        yield ld
    finally:
        session.close()


def fetch_constituents(cfg: dict[str, Any]) -> None:
    """Fetch the current S&P500 constituent list (0#.SPX chain) from LSEG.

    Anchor for reconstructing historical membership from joiner/leaver events.

    Writes: <lseg.constituents_out> (columns: ric)
    """
    out = Path(cfg["lseg"]["constituents_out"])
    with session() as ld:
        df = ld.get_data(universe=["0#.SPX"], fields=["TR.RIC"])
    df = df[["RIC"]].rename(columns={"RIC": "ric"})
    df = df.drop_duplicates().dropna(subset=["ric"])
    store.write_parquet(df, out)
    log.info("wrote %s (%d constituents)", out, len(df))


def fetch_joiners_leavers(cfg: dict[str, Any]) -> None:
    """Read all S&P500 joiner/leaver events from LSEG (records go back to 1994).

    Reads: <lseg.start> (SDATE); EDATE = today
    Writes: <lseg.joiners_leavers_out> (columns: date, ric, name, change)

    Every RIC from this output is probed by fetch_mapping, so ticker/name/PermID stays
    resolvable for delisted and retired (^ -suffixed) instruments.
    """
    c = cfg["lseg"]
    out = Path(c["joiners_leavers_out"])
    with session() as ld:
        df = ld.get_data(
            universe=[".SPX"],
            fields=_JL_FIELDS,
            parameters={
                "SDATE": _api_date(c["start"]),
                "EDATE": _api_date(date.today()),
                "IC": "B",
            },
        )
    keep = [col for col in df.columns if col in _JL_TITLES]
    df = df[keep].rename(columns=_JL_TITLES)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "ric"]).drop_duplicates(subset=["date", "ric", "change"])
    store.write_parquet(df, out)
    log.info("wrote %s (%d events)", out, len(df))


def fetch_mapping(cfg: dict[str, Any]) -> None:
    """Map every known S&P500-related RIC to ticker, company name and PermID.

    PermIDs are permanent (survive delisting/bankruptcy/renames), so this covers
    current and historical constituents alike.

    Reads: <lseg.constituents_out>, <lseg.joiners_leavers_out> (RIC lists)
    Writes: <lseg.mapping_out> (columns: ric, ticker, name, permid)
    """
    c = cfg["lseg"]
    out = Path(c["mapping_out"])
    inputs = [Path(c["constituents_out"]), Path(c["joiners_leavers_out"])]
    missing = [p for p in inputs if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"run lseg-constituents/lseg-joiners-leavers first; missing: {missing}"
        )
    rics = list(pd.concat([pd.read_parquet(p)["ric"] for p in inputs]).dropna().drop_duplicates())
    with session() as ld:
        df = ld.get_data(
            universe=rics,
            fields=["TR.TickerSymbol", "TR.CompanyName", "TR.OrganizationID"],
        )
    df = df.rename(
        columns={
            "Instrument": "ric",
            "Ticker Symbol": "ticker",
            "Company Name": "name",
            "Organization PermID": "permid",
        }
    )[["ric", "ticker", "name", "permid"]]
    df = df.dropna(subset=["ric"])
    store.write_parquet(df, out)
    log.info("wrote %s (%d rics)", out, len(df))


def _normalize(df: pd.DataFrame, titles: dict[str, str]) -> pd.DataFrame:
    """Rename market-cap API output columns to (ric, date, market_cap)."""
    df = df.rename(columns={"Instrument": "ric", **titles})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date", "market_cap"])


def resolve_ric(cfg: dict[str, Any], ric: str) -> str:
    """RIC to query LSEG for content.

    Stale/retired universe RICs are mapped by <lseg.ric_fallbacks> to the RIC
    that carries the same company's content; callers relabel results back.
    """
    return ((cfg.get("lseg") or {}).get("ric_fallbacks") or {}).get(ric, ric)


# RTS back-adjusts price and volume for splits and dividends, keeping both series continuous.
ADJUSTMENTS = "RTS"
_PRICE_FIELDS = ["OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1", "ACVOL_UNS"]
_PRICE_RENAME = {
    "OPEN_PRC": "open",
    "HIGH_1": "high",
    "LOW_1": "low",
    "TRDPRC_1": "close",
    "ACVOL_UNS": "volume",
}
_PRICE_OUT_COLS = ["date", "ric", "open", "high", "low", "close", "volume"]


def _normalize_history(df: pd.DataFrame, ric: str) -> pd.DataFrame:
    """Rename get_history output to (date, ric, open..volume), drop empty rows."""
    df = df.rename(columns=_PRICE_RENAME).rename_axis("date").reset_index()
    df = df.reindex(columns=_PRICE_OUT_COLS)  # some RICs return a (0, 0) frame, not an error
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(None)
    df["ric"] = ric
    df = df.dropna(subset=["close"])
    return df.sort_values(by="date").reset_index(drop=True)


def fetch_history(ld: Any, ric: str, start: str, end: str) -> pd.DataFrame:
    """Fetch adjusted daily OHLCV for one RIC over the whole period.

    Returns the canonical (date, ric, open..volume) frame, empty when the RIC
    has no data. Retired ^-suffixed RICs remain resolvable.
    """
    return _normalize_history(
        ld.get_history(
            universe=ric,
            fields=_PRICE_FIELDS,
            interval="daily",
            start=start,
            end=end,
            adjustments=ADJUSTMENTS,
        ),
        ric,
    )


def fetch_market_cap(cfg: dict[str, Any]) -> None:
    """Fetch quarterly market cap for every known S&P500 RIC.

    Phase 1: TR.CompanyMarketCap (daily-based, quarter-end dates) for all RICs.
    Phase 2: TR.F.MktCap fallback (annual fiscal values, as-of joined in
    build_universe) for retired RICs that phase 1 returned empty.

    Reads: <lseg.constituents_out>, <lseg.joiners_leavers_out> (RIC lists)
    Writes: <lseg.market_cap_out> (columns: ric, date, market_cap)
    """
    c = cfg["lseg"]
    out = Path(c["market_cap_out"])
    inputs = [Path(c["constituents_out"]), Path(c["joiners_leavers_out"])]
    missing = [p for p in inputs if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"run lseg-constituents/lseg-joiners-leavers first; missing: {missing}"
        )
    rics = list(pd.concat([pd.read_parquet(p)["ric"] for p in inputs]).dropna().drop_duplicates())
    params = {
        "SDATE": _api_date(c["start"]),
        "EDATE": _api_date(date.today()),
        "Frq": "Q",
    }
    chunks = [rics[i : i + _MC_CHUNK] for i in range(0, len(rics), _MC_CHUNK)]
    import lseg.data as ld

    ld.get_config().set_param("http.request-timeout", 300)  # default 20s timed out on datagrid
    with session() as ld:
        df = pd.concat(
            [
                _normalize(
                    ld.get_data(universe=chunk, fields=_MC_FIELDS, parameters=params), _MC_TITLES
                )
                for chunk in chunks
            ]
        )
        missing = [r for r in rics if r not in set(df["ric"])]
        if missing:
            fb_chunks = [missing[i : i + _MC_CHUNK] for i in range(0, len(missing), _MC_CHUNK)]
            fb = pd.concat(
                [
                    _normalize(
                        ld.get_data(universe=chunk, fields=_MC_FALLBACK_FIELDS, parameters=params),
                        _MC_FALLBACK_TITLES,
                    )
                    for chunk in fb_chunks
                ]
            )
            df = pd.concat([df, fb])
    df = df.drop_duplicates(subset=["ric", "date"])
    store.write_parquet(df, out)
    log.info("wrote %s (%d rows)", out, len(df))
