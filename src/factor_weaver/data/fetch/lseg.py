"""LSEG data API access: platform session (lseg-data library), S&P500 constituents, prices.

S&P500 membership history is reconstructed (in universe.py) from the current
constituent snapshot as anchor plus joiner/leaver events applied backwards.
Daily prices are cached per universe RIC under <lseg.prices_out>; cached files are
never refetched unless the pipeline runs with --refresh.
"""

import logging
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator, cast

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

# Raw quarterly fundamentals, one request per statement so the statement-level source
# date and original announcement date stay attached to the right fields.
_FUND_IS_FIELDS = [
    "TR.F.TotRevenue",
    "TR.F.COGSTot",
    "TR.F.SGATot",
    "TR.F.IntrExpn",
]
_FUND_BS_FIELDS = [
    "TR.F.ShHoldEqCom",
    "TR.F.TotAssets",
    "TR.F.ComShrOutsTot",
]
_FUND_META_FIELDS = [
    "TR.F.PeriodEndDate",
    "TR.F.SourceDate",
    "TR.F.SourceDate.FundUpdType",
]
_FUND_SUFFIXES = ("", ".date", ".fperiod")

_FUND_OUT_COLS = [
    "ric",
    "field",
    "value",
    "period_end",
    "fiscal_period",
    "source_date",
    "fund_upd_type",
    "original_announcement_date",
]
_FUND_COLUMNS = pd.Index(_FUND_OUT_COLS)

_FUND_IS_REQUEST = [
    f"{field}{suffix}"
    for field in _FUND_IS_FIELDS
    for suffix in _FUND_SUFFIXES
] + _FUND_META_FIELDS + ["TR.ISOriginalAnnouncementDate"]
_FUND_BS_REQUEST = [
    f"{field}{suffix}"
    for field in _FUND_BS_FIELDS
    for suffix in _FUND_SUFFIXES
] + _FUND_META_FIELDS + ["TR.BSOriginalAnnouncementDate"]


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


def resolve_permids(ld: Any, permids: list[str]) -> dict[str, str]:
    """Map company PermIDs to their US consolidated RIC (retired ones keep the ^ suffix).

    The universe is keyed by PermID, so prices follow renames (PSKY.OQ → SKYD.K), and
    consolidated RICs carry consolidated volume (exchange RICs count their venue only).
    """
    df = ld.discovery.convert_symbols(
        symbols=permids,
        from_symbol_type=ld.discovery.SymbolTypes.OA_PERM_ID,
        to_symbol_types=[ld.discovery.SymbolTypes.RIC],
        preferred_country_code=ld.discovery.CountryCode.USA,
    )
    if df.empty or "RIC" not in df.columns:
        return {}
    return {str(k): str(v) for k, v in df["RIC"].dropna().items()}


# RTS back-adjusts price and volume for splits and spin-offs but not cash dividends (closes
# match Yahoo's unadjusted Close); fetch_history folds dividends in from TR.TotalReturn.
ADJUSTMENTS = "RTS"
_TR_FIELDS = ["TR.TotalReturn.date", "TR.TotalReturn"]
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


def _dividend_adjust(df: pd.DataFrame, total_return: pd.DataFrame) -> pd.DataFrame:
    """Back-adjust OHLC for cash dividends, as Yahoo's auto_adjust does.

    A day's factor is its price return over its total return: 1 except on distribution
    days (noise is ~1e-8; spin-off days match because RTS already adjusts them). Each
    day's prices take the product of all later factors.
    """
    tr = pd.Series(
        total_return["Total Return"].astype(float).to_numpy(),
        index=pd.to_datetime(total_return["Date"]).dt.normalize(),
    )
    tr = tr.loc[~tr.index.duplicated(keep="last")]  # retired RICs repeat rows past delisting
    gross = 1 + tr.reindex(df["date"].dt.normalize()).to_numpy() / 100
    factor = pd.Series(df["close"].div(df["close"].shift(1)).to_numpy() / gross)
    factor = factor.where(factor < 1 - 1e-6, 1.0)  # a distribution only lowers the factor
    later = factor.iloc[::-1].cumprod().iloc[::-1].shift(-1, fill_value=1.0)
    cols = ["open", "high", "low", "close"]
    df[cols] = df[cols].mul(later.to_numpy(), axis=0)
    return df


def fetch_history(ld: Any, ric: str, start: str, end: str) -> pd.DataFrame:
    """Fetch split-, spin-off- and dividend-adjusted daily OHLCV for one RIC.

    Returns the canonical (date, ric, open..volume) frame, empty when the RIC
    has no data. Retired ^-suffixed RICs remain resolvable.
    """
    df = _normalize_history(
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
    if df.empty:
        return df
    tr = ld.get_data(
        universe=[ric],
        fields=_TR_FIELDS,
        parameters={"SDate": _api_date(start), "EDate": _api_date(end), "Frq": "D"},
    )
    if tr.empty:
        log.warning("%s: no TR.TotalReturn; prices stay dividend-unadjusted", ric)
        return df
    return _dividend_adjust(df, tr)


def _attempt(fn: Any) -> tuple[pd.DataFrame, str | None]:
    """Run a fetch callable; return (data, error), treating empty as an error."""
    try:
        df = fn()
    except Exception as e:  # the API raises when nothing is found
        return pd.DataFrame(), str(e).splitlines()[0]
    if df.empty:
        return pd.DataFrame(), "no usable rows"
    return df, None


def _same_line(a: str, b: str) -> bool:
    """True when two RICs differ only by venue/retirement suffix (KO.N/KO, AGN.N^E20/AGN^E20)."""
    return a.split("^")[0].split(".")[0] == b.split("^")[0].split(".")[0]


def _covers(df: pd.DataFrame, first: Any, last: Any) -> bool:
    """True when a series spans the RIC's universe membership window.

    Quarter-ends are calendar dates, so the last bar can precede `last` by a weekend or
    holiday (BLS.N^A07 ends 2006-12-29 for the 2006-12-31 window); allow a week.
    """
    return (
        not df.empty
        and df["date"].min() <= first
        and df["date"].max() >= last - pd.DateOffset(days=7)
    )


def _try_lseg(
    ld: Any, ric: str, query: str, start: str, end: str, first: Any, last: Any
) -> tuple[pd.DataFrame, str | None]:
    """Fetch the universe share line covering first..last; rows keep the universe label.

    The PermID-resolved query RIC goes first only when it is the same share line as the
    universe RIC (consolidated volume); otherwise the universe RIC goes first, since
    PermIDs resolve to other classes, preferreds, bonds or when-issued lines (BRKb → BRKa).
    The other candidate is the fallback, which keeps renames working (PSKY.OQ → SKYD.K).
    """
    errors: list[str] = []
    candidates = [query, ric] if _same_line(ric, query) else [ric, query]
    for candidate in dict.fromkeys(candidates):
        df, err = _attempt(lambda c=candidate: fetch_history(ld, c, start, end))
        if err is None and not _covers(df, first, last):
            err = f"no rows covering {first:%Y-%m-%d}..{last:%Y-%m-%d}"
        if err is None:
            if not _same_line(ric, candidate):
                log.warning("%s: priced from %s (different share line)", ric, candidate)
            df["ric"] = ric
            return df, None
        errors.append(f"{candidate}: {err}")
    return pd.DataFrame(), "; ".join(errors)


def fetch_lseg_prices(cfg: dict[str, Any]) -> None:
    """Cache daily OHLCV per registry company (PermID-resolved, universe share line).

    Reads: <universe.assets_out>; window <lseg.start>..<universe.end>: the years before
    universe.start are lookback for technical indicators
    Writes: per-RIC cache under <lseg.prices_out>
    """
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    assets = pd.read_parquet(assets_path)
    cache_dir = Path(cfg["lseg"]["prices_out"])
    start, end = cfg["lseg"]["start"], cfg["universe"]["end"]
    refresh = bool(cfg.get("_refresh"))

    pending: list[tuple[str, str, Path, Any, Any]] = []
    cached = 0
    for row in assets.to_dict("records"):
        ric = str(row["ric"])
        path = store.cache_path(cache_dir, ric, url_quote=True)
        if path.exists() and not refresh:
            cached += 1
            log.debug("  %s: cached", ric)
        else:
            pending.append(
                (ric, str(row["permid"]), path, row["first_quarter_end"], row["last_quarter_end"])
            )

    fetched = 0
    failures: list[tuple[str, str]] = []
    if pending:  # no session/credentials needed when every RIC is cached
        import lseg.data as ld

        ld.get_config().set_param("http.request-timeout", 300)  # default 20s too short for 30y
        with session() as ld:
            query = resolve_permids(ld, sorted({p[1] for p in pending}))
            for ric, permid, path, first, last in pending:
                if permid not in query:
                    log.warning("%s: PermID %s unresolved; using universe RIC", ric, permid)
                df, err = _try_lseg(ld, ric, query.get(permid, ric), start, end, first, last)
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


def _col(df: pd.DataFrame, name: str) -> str | None:
    """Case-insensitive column lookup; None when the API dropped the field."""
    target = name.strip().upper()
    return next((str(c) for c in df.columns if str(c).strip().upper() == target), None)


def _dates(series: pd.Series) -> pd.Series:
    """Parse LSEG date/date-time strings to naive UTC timestamps."""
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None)


def _fund_columns(df: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    """Restore requested names: NAME headers repeat the base field for each suffix column."""
    buckets: dict[str, list[int]] = {}
    for i, col in enumerate(df.columns):
        buckets.setdefault(str(col).strip().upper(), []).append(i)
    columns = [str(c) for c in df.columns]
    for field in fields:
        base = ".".join(field.split(".")[:3]).upper()
        positions = buckets.get(base)
        if positions:
            columns[positions.pop(0)] = field
    return df.set_axis(pd.Index(columns), axis=1)


def _normalize_fundamentals(
    df: pd.DataFrame, ric: str, fields: list[str], announcement_col: str
) -> pd.DataFrame:
    """Long (ric, field, value, period_end, metadata) rows from one statement response.

    Rows of one response need not describe one period (GS revenue, NOW equity after
    fiscal-year changes), so each field is keyed by its own .date and the statement
    metadata is joined on PeriodEndDate rather than taken from the same row.
    """
    if df.empty:
        return pd.DataFrame(columns=_FUND_COLUMNS)

    def text(name: str) -> pd.Series:
        col = _col(df, name)
        if col is None:
            return pd.Series(pd.NA, index=df.index, dtype="string")
        return cast(pd.Series, df[col]).astype("string")

    def days(name: str) -> pd.Series:
        col = _col(df, name)
        return _dates(cast(pd.Series, df[col])) if col else pd.Series(pd.NaT, index=df.index)

    meta = (
        pd.DataFrame(
            {
                "period_end": days("TR.F.PeriodEndDate"),
                "source_date": days("TR.F.SourceDate"),
                "fund_upd_type": text("TR.F.SourceDate.FundUpdType"),
                "original_announcement_date": days(announcement_col),
            }
        )
        .dropna(subset=["period_end"])
        .sort_values("source_date", kind="stable")  # NaT last: keep the dated copy
        .drop_duplicates("period_end")
    )

    frames: list[pd.DataFrame] = []
    for field in fields:
        value_col = _col(df, field)
        if value_col is None:
            log.warning("%s: field %s not returned; skipped", ric, field)
            continue
        frame = pd.DataFrame(
            {
                "field": field,
                "value": pd.to_numeric(df[value_col], errors="coerce"),
                "period_end": days(f"{field}.date"),
                "fiscal_period": text(f"{field}.fperiod"),
            }
        ).dropna(subset=["value"])
        undated = int(frame["period_end"].isna().sum())
        if undated:
            log.debug("%s: %s has %d values without a date; dropped", ric, field, undated)
        frames.append(frame.dropna(subset=["period_end"]))
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=_FUND_COLUMNS)
    out = pd.concat(frames, ignore_index=True).merge(meta, on="period_end", how="left")
    out["ric"] = ric
    out["value"] = out["value"].astype("float64")
    return (
        out.drop_duplicates(["field", "period_end"])
        .sort_values(["period_end", "field"])
        .reindex(columns=_FUND_COLUMNS)
        .reset_index(drop=True)
    )


def _fund_params(start: str, end: str, consolidated: bool = True) -> dict[str, str]:
    params = {
        "SDATE": _api_date(start),
        "EDATE": _api_date(end),
        "Period": "FQ0",
        "Frq": "FQ",
        "ReportingState": "Orig",
        "Curn": "USD",
        "FXRate": "PeriodEnd",
        "Scale": "0",
    }
    if consolidated:
        params["ConsolBasis"] = "Consolidated"
    return params


def _fetch_statement(ld: Any, ric: str, start: str, end: str, fields: list[str]) -> pd.DataFrame:
    """Fetch one statement as originally reported, consolidated basis first.

    No ReportingState=All fallback: restated values would pass as originals.
    The date row header does not guarantee one period per row;
    _normalize_fundamentals joins on each field's own date.
    """
    fr = ld.content.fundamental_and_reference
    last: Exception = RuntimeError("empty response")
    for consolidated in (True, False):
        try:
            response = fr.Definition(
                [ric],
                fields,
                parameters=_fund_params(start, end, consolidated),
                row_headers=[fr.RowHeaders.DATE],
                header_type=ld.HeaderType.NAME,
            ).get_data()
            if not response.is_success:
                raise RuntimeError(f"request failed: {response.errors}")
            df = response.data.df
        except Exception as e:
            last = e
            continue
        if not df.empty:
            return _fund_columns(df, fields)
        last = RuntimeError("empty response")
    raise last


def _try_fundamentals(
    ld: Any, ric: str, candidates: list[str], start: str, end: str
) -> tuple[pd.DataFrame, str | None]:
    """Fetch both statements for the first candidate RIC that answers."""
    errors: list[str] = []
    for candidate in dict.fromkeys(candidates):
        is_df, is_err = _attempt(
            lambda: _fetch_statement(ld, candidate, start, end, _FUND_IS_REQUEST)
        )
        bs_df, bs_err = _attempt(
            lambda: _fetch_statement(ld, candidate, start, end, _FUND_BS_REQUEST)
        )
        if is_err is None and bs_err is None:
            df = pd.concat(
                [
                    _normalize_fundamentals(
                        is_df, ric, _FUND_IS_FIELDS, "TR.ISOriginalAnnouncementDate"
                    ),
                    _normalize_fundamentals(
                        bs_df, ric, _FUND_BS_FIELDS, "TR.BSOriginalAnnouncementDate"
                    ),
                ],
                ignore_index=True,
            )
            if df.empty:
                errors.append(f"{candidate}: no values")
                continue
            return df.sort_values(["period_end", "field"], ignore_index=True), None
        errors.append(f"{candidate}: IS {is_err or 'ok'}; BS {bs_err or 'ok'}")
    return pd.DataFrame(columns=_FUND_COLUMNS), "; ".join(errors)


def fetch_fundamentals(cfg: dict[str, Any]) -> None:
    """Cache raw quarterly fundamentals per universe RIC (statement-level metadata).

    Reads: <universe.assets_out>; window <lseg.start>..<universe.end>: the years before
    universe.start are lookback for 36-month net issuance and 4-quarter growth
    Writes: per-RIC cache under <lseg.fundamentals_out>
    """
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    assets = pd.read_parquet(assets_path)
    cache_dir = Path(cfg["lseg"]["fundamentals_out"])
    start, end = cfg["lseg"]["start"], cfg["universe"]["end"]
    refresh = bool(cfg.get("_refresh"))

    pending: list[tuple[str, str, Path]] = []
    cached = 0
    for row in assets.to_dict("records"):
        ric = str(row["ric"])
        path = store.cache_path(cache_dir, ric, url_quote=True)
        if path.exists() and not refresh:
            cached += 1
            log.debug("  %s: cached", ric)
        else:
            pending.append((ric, str(row["permid"]), path))

    fetched = 0
    failures: list[tuple[str, str]] = []
    if pending:  # no session/credentials needed when every RIC is cached
        with session() as ld:
            ld.get_config().set_param("http.request-timeout", 300)
            query = resolve_permids(ld, sorted({p[1] for p in pending}))
            for ric, permid, path in pending:
                resolved = query.get(permid)
                candidates = [ric, resolved] if resolved and resolved != ric else [ric]
                df, err = _try_fundamentals(ld, ric, candidates, start, end)
                if err is not None:
                    failures.append((ric, err))
                    log.debug("  %s: failed (%s)", ric, err)
                    continue
                store.write_parquet(df, path)
                fetched += 1
                log.debug("  %s: %d fundamental rows", ric, len(df))

    log.info(
        "lseg-fundamentals: %d cached, %d fetched, %d failed (%d rics)",
        cached,
        fetched,
        len(failures),
        len(assets),
    )
    for ric, err in failures:
        log.warning("  %s: %s", ric, err)
    if cached + fetched == 0 and len(assets):
        raise RuntimeError(f"no LSEG fundamental data fetched; failures: {failures}")
