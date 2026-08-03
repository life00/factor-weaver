"""LSEG data API access: platform session (lseg-data library) + S&P500 constituents.

S&P500 membership history is reconstructed (in universe.py) from the current
constituent snapshot as anchor plus joiner/leaver events applied backwards.
"""

import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from dotenv import load_dotenv

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


def _credentials() -> dict[str, str]:
    """Read LSEG credentials from .env (loaded into os.environ if present)."""
    load_dotenv()
    values = {name: os.getenv(name) for name in _ENV_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"missing LSEG credentials in .env: {', '.join(missing)}")
    return {name: value for name, value in values.items() if value is not None}


@contextmanager
def _session() -> Iterator[Any]:
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
    with _session() as ld:
        df = ld.get_data(universe=["0#.SPX"], fields=["TR.RIC"])
    df = df[["RIC"]].rename(columns={"RIC": "ric"})
    df = df.drop_duplicates().dropna(subset=["ric"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"wrote {out} ({len(df)} constituents)")


def fetch_joiners_leavers(cfg: dict[str, Any]) -> None:
    """Read all S&P500 joiner/leaver events from LSEG (records go back to 1994).

    Reads: <lseg.start> (SDATE); EDATE = today
    Writes: <lseg.joiners_leavers_out> (columns: date, ric, name, change)

    Every RIC from this output is probed by fetch_mapping, so ticker/name/PermID stays
    resolvable for delisted and retired (^ -suffixed) instruments.
    """
    c = cfg["lseg"]
    out = Path(c["joiners_leavers_out"])
    with _session() as ld:
        df = ld.get_data(
            universe=[".SPX"],
            fields=_JL_FIELDS,
            parameters={
                "SDATE": c["start"],
                "EDATE": date.today().strftime("%Y%m%d"),
                "IC": "B",
            },
        )
    keep = [col for col in df.columns if col in _JL_TITLES]
    df = df[keep].rename(columns=_JL_TITLES)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "ric"]).drop_duplicates(subset=["date", "ric", "change"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"wrote {out} ({len(df)} events)")


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
    with _session() as ld:
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
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"wrote {out} ({len(df)} rics)")
