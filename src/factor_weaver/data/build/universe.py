import logging
from pathlib import Path
from typing import Any

import pandas as pd

from factor_weaver.data import store

log = logging.getLogger(__name__)

_OUT_COLS: list[str] = ["quarter_end", "ric", "permid", "ticker", "delisted", "marketcap", "rank"]
_ASSET_COLS: list[str] = [
    "ric",
    "ticker",
    "name",
    "permid",
    "delisted",
    "first_quarter_end",
    "last_quarter_end",
]


def build_universe(cfg: dict[str, Any]) -> None:
    """Build the dynamic top-N S&P500 universe by market cap per quarter.

    Reconstructs quarterly S&P500 membership backwards from the current
    constituent snapshot using joiner/leaver events (Joiner events remove a
    RIC when walking back, Leaver events add it), then ranks active members
    by as-of market cap (latest value at or before the quarter-end) and
    keeps the top N per quarter. RICs in <universe.exclude_rics> are dropped
    before ranking, so the next-ranked company backfills their slot.
    RICs without a PermID mapping are dropped. Candidates are deduplicated by
    LSEG PermID before ranking (company-level market cap), keeping the RIC with
    the most membership quarters, then alphabetical.

    Reads: <lseg.constituents_out>, <lseg.joiners_leavers_out>,
           <lseg.mapping_out>, <lseg.market_cap_out>
    Writes: <universe.universe_out> (columns: quarter_end, ric, permid, ticker, delisted,
            marketcap, rank). Delisted RICs have no LSEG ticker; their ticker
            is the base RIC symbol (e.g. TWX.N^A01 -> TWX) and delisted=True.
            <universe.assets_out> (columns: ric, ticker, name, permid,
            delisted, first/last_quarter_end): one row per distinct universe
            RIC, the global asset registry for downstream steps.
    """
    c = cfg["lseg"]
    u = cfg["universe"]
    out = Path(u["universe_out"])
    inputs = {
        "constituents_out": Path(c["constituents_out"]),
        "joiners_leavers_out": Path(c["joiners_leavers_out"]),
        "mapping_out": Path(c["mapping_out"]),
        "market_cap_out": Path(c["market_cap_out"]),
    }
    missing = [p for p in inputs.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"run earlier data steps first; missing: {missing}")

    constituents: pd.DataFrame = pd.read_parquet(inputs["constituents_out"])
    events_raw: pd.DataFrame = pd.read_parquet(inputs["joiners_leavers_out"])
    anchor = set(constituents["ric"])
    events = events_raw.loc[:, ["date", "ric", "change"]]
    events = events.sort_values(by="date", ascending=False).reset_index(drop=True)

    quarters = pd.date_range(pd.Timestamp(u["start"]), pd.Timestamp(u["end"]), freq="QE")
    active: dict[pd.Timestamp, list[str]] = {}
    members = set(anchor)
    i = 0
    baseline = events["date"].min()
    for q in quarters[::-1]:
        while i < len(events) and events.loc[i, "date"] > q.to_datetime64():
            ric, change = events.loc[i, "ric"], events.loc[i, "change"]
            if change == "Joiner" and events.loc[i, "date"] > baseline:
                members.discard(ric)
            elif change == "Leaver":
                members.add(ric)
            i += 1
        active[q] = list(members)

    rows = [(q, ric) for q, rics in active.items() for ric in rics]
    active_df = pd.DataFrame({"quarter_end": [q for q, _ in rows], "ric": [ric for _, ric in rows]})
    mc_raw: pd.DataFrame = pd.read_parquet(inputs["market_cap_out"])
    active_df["ric"] = active_df["ric"].astype(mc_raw["ric"].dtype)
    mc = mc_raw.loc[:, ["ric", "date", "market_cap"]]
    merged: pd.DataFrame = pd.merge_asof(
        active_df.sort_values(by="quarter_end"),
        mc.sort_values(by="date"),
        left_on="quarter_end",
        right_on="date",
        by="ric",
        direction="backward",
    )
    # some retired RICs have no cap data at all
    # dropping them does not affect top 50
    merged = merged.dropna(subset=["market_cap"]).rename(columns={"market_cap": "marketcap"})
    exclude = list(u.get("exclude_rics") or [])
    if exclude:
        merged = merged.loc[~merged["ric"].isin(exclude)]
    mapping_raw: pd.DataFrame = pd.read_parquet(inputs["mapping_out"])
    mapping = mapping_raw.loc[:, ["ric", "ticker", "name", "permid"]].drop_duplicates(subset="ric")
    merged = merged.merge(mapping, on="ric").dropna(subset=["permid"])
    # TR.CompanyMarketCap is per company: share classes (GOOG/GOOGL) carry the same cap.
    # Rank companies, one RIC per PermID: the longest S&P member, then alphabetical.
    member_quarters = active_df["ric"].value_counts().rename("member_quarters")
    merged = merged.merge(member_quarters, left_on="ric", right_index=True, how="left")
    merged = merged.sort_values(by=["member_quarters", "ric"], ascending=[False, True])
    merged = merged.drop_duplicates(subset=["quarter_end", "permid"])
    merged["rank"] = (
        merged.groupby("quarter_end")["marketcap"].rank(ascending=False, method="first").astype(int)
    )
    merged = merged.loc[merged["rank"] <= u["top_n"]]
    per_q = merged.groupby("quarter_end").size()
    if (per_q < u["top_n"]).any():
        log.warning(
            "%d quarters rank fewer than %d members", int((per_q < u["top_n"]).sum()), u["top_n"]
        )
    df = merged
    # LSEG returns no ticker for most retired RICs (^-suffixed)
    # generate the base symbol from the RIC (TWX.N^A01 -> TWX) and flag the row as delisted
    df["delisted"] = df["ticker"].isna()
    df["ticker"] = df["ticker"].fillna(df["ric"].str.split(".").str[0])

    assets = (
        df.groupby("ric", as_index=False)
        .agg(
            ticker=("ticker", "first"),
            name=("name", "first"),
            permid=("permid", "first"),
            delisted=("delisted", "first"),
            first_quarter_end=("quarter_end", "min"),
            last_quarter_end=("quarter_end", "max"),
        )
        .loc[:, _ASSET_COLS]
    )
    # one asset per PermID: collapsing RICs would silently mix share lines; fix upstream
    dup = assets.loc[assets["permid"].duplicated(keep=False)]
    if not dup.empty:
        pairs = dup[["permid", "ric"]].to_dict("records")
        raise ValueError(f"PermIDs with several universe RICs: {pairs}")
    assets_out = Path(u["assets_out"])
    store.write_parquet(assets, assets_out)

    df = df.loc[:, _OUT_COLS].sort_values(by=["quarter_end", "rank"])
    store.write_parquet(df, out)
    log.info("wrote %s (%d rows, %d quarters)", out, len(df), df["quarter_end"].nunique())
    log.info("wrote %s (%d assets)", assets_out, len(assets))
