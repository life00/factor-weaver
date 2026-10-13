"""MarketPsych Analytics Files API: daily buzz (attention) + sentiment per asset.

One listing call per configured window, then one verbatim payload per listed file
(monthly `PRO.Archive` zips for complete months, daily `PRO.Live` TSVs for the
current month) under <marketpsych.raw_out>/files/, each next to a universe-filtered
parquet slice. Slices are written per file and never re-parsed while present unless
the pipeline runs with --refresh, which re-parses the kept payloads and downloads
only the missing ones. Slices are filtered to <universe.assets_out>, so a universe
change needs a fetch run with --refresh; the build step broadcasts the PermID-keyed
series to every RIC sharing it.
"""

import json
import logging
import os
import random
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from factor_weaver.data import store

log = logging.getLogger(__name__)

_BASE = "https://dataapi.marketpsych.com/rma/v4/files"
_ENV_VAR = "MARKETPSYCH_API_KEY"
_TIMEOUT = 120  # seconds per HTTP call
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


def _request(url: str) -> Any:
    """GET a data URL, retrying throttles and 5xx; the URL carries the key, never log it."""
    _throttle()
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return urllib.request.urlopen(url, timeout=_TIMEOUT)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            retry_after = (e.headers.get("Retry-After") if e.headers else None) or 0
            if not (e.code == 429 or 500 <= e.code < 600) or attempt == _MAX_ATTEMPTS:
                raise RuntimeError(f"marketpsych api error {e.code}: {body[:300]}") from None
            wait = max(float(retry_after), _BACKOFF_BASE**attempt + random.uniform(0, 0.5))
            log.warning(
                "marketpsych: http %d, retry %d/%d in %.1fs", e.code, attempt, _MAX_ATTEMPTS, wait
            )
        except urllib.error.URLError as e:  # timeouts, resets, DNS
            if attempt == _MAX_ATTEMPTS:
                raise RuntimeError(
                    f"marketpsych request failed after {_MAX_ATTEMPTS} attempts: {e.reason}"
                ) from None
            wait = _BACKOFF_BASE**attempt + random.uniform(0, 0.5)
            log.warning(
                "marketpsych: %s, retry %d/%d in %.1fs", e.reason, attempt, _MAX_ATTEMPTS, wait
            )
        time.sleep(wait)
    raise RuntimeError(f"marketpsych request failed after {_MAX_ATTEMPTS} attempts")


def list_files(asset_class: str, frequency: str, start: str, end: str) -> list[dict[str, Any]]:
    """List the payload files covering [start, end); downloads are pre-signed links."""
    query = urllib.parse.urlencode({"apikey": api_key(), "start_date": start, "end_date": end})
    return json.loads(_request(f"{_BASE}/{asset_class}/{frequency}?{query}").read())["data"]


def download(link: str, path: Path) -> None:
    """Stream one payload to path via a temp file, so an interrupted transfer is no cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with _request(link) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    tmp.replace(path)


def read_slice(
    payload: Path, permids: pd.Index, datatypes: set[str], datacols: list[str]
) -> pd.DataFrame:
    """Parse one payload (TSV, or a zip holding one TSV) into universe-filtered RAW_COLS."""
    if payload.suffix == ".zip":
        with zipfile.ZipFile(payload) as archive:
            members = [name for name in archive.namelist() if name.endswith(".txt")]
            if len(members) != 1:
                raise RuntimeError(
                    f"marketpsych: {payload.name}: expected one .txt member, found {members}"
                )
            with archive.open(members[0]) as handle:
                return _parse(handle, payload, permids, datatypes, datacols)
    with payload.open("rb") as handle:
        return _parse(handle, payload, permids, datatypes, datacols)


def _parse(
    handle: Any, payload: Path, permids: pd.Index, datatypes: set[str], datacols: list[str]
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
    keep = out["source"].isin(list(datatypes)) & out["permid"].isin(permids.tolist())
    out = out.loc[keep]
    return out.reindex(columns=RAW_COLS).drop_duplicates(subset=["permid", "date", "source"])


def fetch_marketpsych(cfg: dict[str, Any]) -> None:
    """Download the listed payloads and write one universe-filtered slice per payload.

    Reads: <universe.assets_out>
    Writes: <marketpsych.raw_out>/files/<filename>, <marketpsych.raw_out>/<filename>.parquet
    """
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    permids = pd.Index(
        sorted(pd.read_parquet(assets_path, columns=["permid"])["permid"].astype(str).unique())
    )
    mp = cfg["marketpsych"]
    datatypes = {d.lower() for d in mp["datatypes"]}
    raw = Path(mp["raw_out"])
    payload_dir = raw / "files"
    entries = list_files(mp["asset_class"], mp["frequency"], mp["start"], mp["end"])
    pending = [
        e
        for e in entries
        if cfg.get("_refresh") or not store.cache_path(raw, e["filename"]).exists()
    ]
    if not pending:
        log.info("marketpsych: all file caches present in %s", raw)
        return
    log.info(
        "marketpsych: %d files (%.2f GiB) to fetch",
        len(pending),
        sum(e["size"] for e in pending) / 2**30,
    )
    for entry in pending:
        payload = payload_dir / entry["filename"]
        if not payload.exists():  # kept payloads are re-parsed, never re-downloaded
            log.info("marketpsych: %s (%.1f MB)", entry["filename"], entry["size"] / 1e6)
            download(entry["link"], payload)
        slice_path = store.cache_path(raw, entry["filename"])
        slice = read_slice(payload, permids, datatypes, mp["datacols"])
        store.write_parquet(slice, slice_path)
        log.info("wrote %s (%d rows)", slice_path, len(slice))
    log.info("marketpsych: %d file caches in %s", len(pending), raw)
