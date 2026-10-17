"""MarketPsych Analytics Files API: daily buzz (attention) + sentiment per asset.

One listing call per configured asset class, then one verbatim payload per listed file
(monthly `PRO.Archive` zips for complete months, daily `PRO.Live` TSVs for the
current month) under <marketpsych.raw_out>/files/, each next to a universe-filtered
parquet slice. Slices are written per file and never re-parsed while present unless
the pipeline runs with --refresh, which re-parses the kept payloads and downloads
only the missing ones. Slices are filtered to <universe.assets_out> after re-keying the
vendor assetCodes through aliases generated from the cached asset reference
(<marketpsych.reference_out>, GET /rma/v4/equ/assets), so a universe change needs a fetch
run with --refresh; the build step broadcasts the PermID-keyed series to every RIC sharing it.
"""

import http.client
import json
import logging
import os
import random
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from dotenv import load_dotenv

from factor_weaver.data import store

log = logging.getLogger(__name__)

_BASE = "https://dataapi.marketpsych.com/rma/v4/files"
_REFERENCE_URL = "https://dataapi.marketpsych.com/rma/v4/equ/assets"
_ENV_VAR = "MARKETPSYCH_API_KEY"
_TIMEOUT = 120  # seconds per HTTP call
_REFERENCE_TIMEOUT = 600  # seconds; the asset reference is one ~148k-row JSON body (~80 s here)
_MIN_INTERVAL = 1.0  # seconds between request starts
_MAX_ATTEMPTS = 5
_BACKOFF_BASE = 2.0  # retry waits ≈2, 4, 8, 16 s (+ jitter, or Retry-After when larger)
RAW_COLS = ["permid", "date", "source", "buzz", "sentiment"]
_RENAME = {"assetCode": "permid", "windowTimestamp": "date", "dataType": "source"}

_last_request = 0.0


def api_key() -> str:
    """Read the API key from .env (never logged, echoed or written to a file)."""
    load_dotenv()
    key = os.getenv(_ENV_VAR)
    if not key:
        raise RuntimeError(f"{_ENV_VAR} missing from .env")
    return key


def _throttle() -> None:
    """Client-side pacing: at least _MIN_INTERVAL between request starts."""
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request = time.monotonic()


def _open(url: str, offset: int = 0) -> Any:
    """One GET attempt; offset > 0 asks for the rest of a partially transferred payload."""
    _throttle()
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=_TIMEOUT)


def _open_reference(url: str) -> Any:
    """One GET attempt for the asset reference; a single large body gets a longer deadline."""
    _throttle()
    return urllib.request.urlopen(url, timeout=_REFERENCE_TIMEOUT)


def _retry(op: Callable[[], Any], what: str) -> Any:
    """Run one request attempt up to _MAX_ATTEMPTS; retry throttles, 5xx and network faults.

    The URL carries the key (listing) or a pre-signed token (download) — never log it.
    """
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return op()
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode(errors="replace")
            except OSError:  # the error response itself was cut off
                body = ""
            retry_after = (e.headers.get("Retry-After") if e.headers else None) or 0
            if not (e.code == 429 or 500 <= e.code < 600) or attempt == _MAX_ATTEMPTS:
                raise RuntimeError(f"marketpsych: {what}: http {e.code}: {body[:300]}") from None
            wait = max(float(retry_after), _BACKOFF_BASE**attempt + random.uniform(0, 0.5))
            log.warning(
                "marketpsych: %s: http %d, retry %d/%d in %.1fs",
                what, e.code, attempt, _MAX_ATTEMPTS, wait,
            )
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            # resets, timeouts, DNS, truncated bodies — a half-read response is no file
            reason = getattr(e, "reason", e)
            if attempt == _MAX_ATTEMPTS:
                raise RuntimeError(
                    f"marketpsych: {what}: failed after {_MAX_ATTEMPTS} attempts: {reason}"
                ) from None
            wait = _BACKOFF_BASE**attempt + random.uniform(0, 0.5)
            log.warning(
                "marketpsych: %s: %s, retry %d/%d in %.1fs",
                what,
                reason,
                attempt,
                _MAX_ATTEMPTS,
                wait,
            )
        time.sleep(wait)
    raise RuntimeError(f"marketpsych: {what}: failed after {_MAX_ATTEMPTS} attempts")


def _get_reference() -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"apikey": api_key()})
    with _open_reference(f"{_REFERENCE_URL}?{query}") as response:
        payload = json.loads(response.read())
    if "data" not in payload:  # outside _retry's set: a malformed body fails at once
        raise RuntimeError("marketpsych: asset reference: missing data")
    return payload["data"]


_REFERENCE_COLS = ["permid", "name", "ric", "ticker", "status", "current_permid"]


def _id(value: Any) -> str:
    """A PermID as str; JSON carries them as ints, floats (with nulls) or strings."""
    if value is None or value == "":
        return ""
    return str(int(value)) if isinstance(value, float) else str(value)


def _normalize_reference(payload: list[dict[str, Any]]) -> pd.DataFrame:
    """Vendor asset reference → one row per assetCode with its current company PermID."""
    if not payload:
        return pd.DataFrame(columns=pd.Index(_REFERENCE_COLS))
    for column in ("assetCode", "CurrentInstrumentIssuerPermid"):
        if column not in payload[0]:
            raise RuntimeError(f"marketpsych: asset reference: missing {column}")
    rows: dict[str, dict[str, Any]] = {}  # assetCode → row; a later row supersedes
    for row in payload:
        permid = _id(row["assetCode"])
        if not permid:
            continue
        rows[permid] = {
            "permid": permid,
            "name": row.get("name"),
            "ric": row.get("RIC"),
            "ticker": row.get("Ticker"),
            "status": row.get("status"),
            "current_permid": _id(row["CurrentInstrumentIssuerPermid"]) or permid,
        }
    return pd.DataFrame(list(rows.values()))


def load_reference(cfg: dict[str, Any]) -> tuple[pd.DataFrame, bool]:
    """Cached asset reference, plus whether it was fetched now (a fetch re-parses every slice)."""
    path = Path(cfg["marketpsych"]["reference_out"])
    if cfg.get("_refresh") or not path.exists():
        df = _normalize_reference(_retry(_get_reference, "asset reference"))
        store.write_parquet(df, path)
        log.info("wrote %s (%d reference rows)", path, len(df))
        return df, True
    return pd.read_parquet(path), False


_NAME_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "plc",
    "ltd",
    "limited",
    "llc",
    "holdings",
    "holding",
    "group",
    "sa",
    "nv",
    "ag",
    "se",
    "trust",
}


def _name_key(name: Any) -> str:
    if pd.isna(name):
        return ""
    tokens = re.findall(r"[a-z0-9]+", str(name).lower())
    return "".join(token for token in tokens if token not in _NAME_SUFFIXES)


def build_aliases(assets: pd.DataFrame, reference: pd.DataFrame) -> dict[str, str]:
    """MP assetCode → universe PermID, from the vendor asset reference alone.

    `CurrentInstrumentIssuerPermid` links a pre-merger/pre-reincorporation code to the current
    company; a normalized-name match covers unlinked legal entities (the reference keeps XOM's
    two entities apart). A universe PermID is never rewritten — those rows already match.
    """
    universe = set(assets["permid"].astype(str))
    live = sorted(universe)  # a sequence: pandas isin is typed for sequences
    aliases: dict[str, str] = {}
    successors = 0
    linked = reference[
        reference["current_permid"].isin(live) & reference["permid"].ne(reference["current_permid"])
    ]
    for old, targets in linked.groupby("permid")["current_permid"]:
        targets = sorted(set(targets))
        if len(targets) > 1:
            log.warning("marketpsych: reference links %s to %s; link dropped", old, targets)
            continue
        if str(old) in universe:  # a rewrite would drop the rows already keyed right
            continue
        aliases[str(old)] = targets[0]
        successors += 1
    in_universe = reference["permid"].isin(live)
    names: dict[str, set[str]] = {}
    universe_rows = reference.loc[in_universe]
    for permid, name in zip(universe_rows["permid"], universe_rows["name"]):
        key = _name_key(name)
        if key:
            names.setdefault(key, set()).add(permid)
    unique: dict[str, str] = {}
    for key, permids in names.items():
        if len(permids) > 1:
            log.warning(
                "marketpsych: %r names %d universe PermIDs; name fallback skipped",
                key,
                len(permids),
            )
        else:
            unique[key] = next(iter(permids))
    no_ric = reference["ric"].isna() | reference["ric"].astype(str).str.strip().eq("")
    no_ticker = reference["ticker"].isna() | reference["ticker"].astype(str).str.strip().eq("")
    unlinked = reference[
        ~in_universe
        & reference["permid"].eq(reference["current_permid"])  # not a successor-linked code
        & no_ric
        & no_ticker  # a legal entity, not an operating listing
    ]
    named = 0
    for permid, name in zip(unlinked["permid"], unlinked["name"]):
        key = _name_key(name)
        if key in unique and permid not in aliases:
            aliases[permid] = unique[key]
            named += 1
    log.info(
        "marketpsych: %d successor links, %d name-fallback links, %d universe PermIDs"
        " missing from the reference",
        successors,
        named,
        len(universe - set(reference["permid"])),
    )
    log.debug("marketpsych: aliases %s", aliases)
    return aliases


def list_files(asset_class: str, frequency: str, start: str, end: str) -> list[dict[str, Any]]:
    """List the payload files covering [start, end); downloads are pre-signed links."""
    query = urllib.parse.urlencode({"apikey": api_key(), "start_date": start, "end_date": end})
    url = f"{_BASE}/{asset_class}/{frequency}?{query}"

    def attempt() -> list[dict[str, Any]]:
        with _open(url) as response:
            return json.loads(response.read())["data"]

    return _retry(attempt, f"{asset_class}/{frequency} listing")


def download(link: str, path: Path) -> None:
    """Stream one payload to path; a reset transfer resumes, the file lands atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)  # scratch from an aborted run, not a resume point

    def attempt() -> None:
        offset = tmp.stat().st_size if tmp.exists() else 0
        with _open(link, offset) as response:
            # the pre-signed link supports ranges; a 200 means it ignored ours → start over
            mode = "ab" if offset and response.status == 206 else "wb"
            with tmp.open(mode) as handle:
                shutil.copyfileobj(response, handle)

    _retry(attempt, path.name)
    tmp.replace(path)


def read_slice(
    payload: Path,
    permids: pd.Index,
    datatypes: set[str],
    datacols: list[str],
    aliases: dict[str, str],
) -> pd.DataFrame:
    """Parse one payload (TSV, or a zip holding one TSV) into universe-filtered RAW_COLS.

    Rows keyed on an aliased MP permid are re-keyed to the universe permid.
    """
    if payload.suffix == ".zip":
        with zipfile.ZipFile(payload) as archive:
            members = [name for name in archive.namelist() if name.endswith(".txt")]
            if len(members) != 1:
                raise RuntimeError(
                    f"marketpsych: {payload.name}: expected one .txt member, found {members}"
                )
            with archive.open(members[0]) as handle:
                return _parse(handle, payload, permids, datatypes, datacols, aliases)
    with payload.open("rb") as handle:
        return _parse(handle, payload, permids, datatypes, datacols, aliases)


def _parse(
    handle: Any,
    payload: Path,
    permids: pd.Index,
    datatypes: set[str],
    datacols: list[str],
    aliases: dict[str, str],
) -> pd.DataFrame:
    cols = ["assetCode", "windowTimestamp", "dataType", *datacols]
    try:
        df = pd.read_csv(handle, sep="\t", usecols=pd.Index(cols))
    except ValueError as e:  # a column the payload does not have
        raise RuntimeError(f"marketpsych: {payload.name}: {e}") from None
    out = df.rename(columns=_RENAME)
    out["permid"] = out["permid"].astype(str)
    out["date"] = pd.to_datetime(out["date"], utc=True).dt.tz_convert(None).dt.normalize()
    out["source"] = out["source"].str.lower()
    out["permid"] = out["permid"].replace(aliases)  # MP assetCode → universe permid
    keep = out["source"].isin(list(datatypes)) & out["permid"].isin(permids.tolist())
    out = out.loc[keep]
    return out.reindex(columns=RAW_COLS).drop_duplicates(subset=["permid", "date", "source"])


def fetch_marketpsych(cfg: dict[str, Any]) -> None:
    """Download the listed payloads and write one universe-filtered slice per payload.

    Reads: <universe.assets_out>, <marketpsych.reference_out>
    Writes: <marketpsych.raw_out>/files/<filename>, <marketpsych.raw_out>/<filename>.parquet
    """
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    assets = pd.read_parquet(assets_path, columns=["permid"])
    assets["permid"] = assets["permid"].astype(str)
    permids = pd.Index(sorted(assets["permid"].unique()))
    mp = cfg["marketpsych"]
    datatypes = {d.lower() for d in mp["datatypes"]}
    raw = Path(mp["raw_out"])
    payload_dir = raw / "files"
    entries = [
        entry
        for cls in mp["asset_classes"]
        for entry in list_files(cls, mp["frequency"], mp["start"], mp["end"])
    ]
    reference, reference_fetched = load_reference(cfg)
    aliases = build_aliases(assets, reference)
    pending = [
        e
        for e in entries
        if cfg.get("_refresh") or not store.cache_path(raw, e["filename"]).exists()
    ]
    if reference_fetched:  # a new map or a universe change re-keys rows already on disk
        log.info("marketpsych: reference fetched; re-parsing all %d slices", len(entries))
        pending = entries
    if not pending:
        log.info("marketpsych: all file caches present in %s", raw)
        return
    missing = [e for e in pending if not (payload_dir / e["filename"]).exists()]
    log.info(
        "marketpsych: %d files (%.2f GiB) to download, %d slices to write",
        len(missing),
        sum(e["size"] for e in missing) / 2**30,
        len(pending),
    )
    for entry in pending:
        payload = payload_dir / entry["filename"]
        if not payload.exists():  # kept payloads are re-parsed, never re-downloaded
            log.info("marketpsych: %s (%.1f MB)", entry["filename"], entry["size"] / 1e6)
            download(entry["link"], payload)
        slice_path = store.cache_path(raw, entry["filename"])
        slice = read_slice(payload, permids, datatypes, mp["datacols"], aliases)
        store.write_parquet(slice, slice_path)
        log.info("wrote %s (%d rows)", slice_path, len(slice))
    log.info("marketpsych: %d file caches in %s", len(pending), raw)
