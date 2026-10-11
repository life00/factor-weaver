"""MarketPsych Analytics pull API: daily buzz (attention) + sentiment per asset.

One parquet cache per calendar month under <marketpsych.raw_out>; the build step
broadcasts the PermID-keyed series to every RIC sharing it. Cached months are
never re-requested unless the pipeline runs with --refresh.
"""

import io
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

import pandas as pd
from dotenv import load_dotenv

from factor_weaver.data import store

log = logging.getLogger(__name__)

_ENTRY = "https://dataapi.marketpsych.com/rma/v4/data"
_ENV_VAR = "MARKETPSYCH_API_KEY"
_MAX_ASSET_DAYS = 15_000  # documented pull limit per query (freq=dai)
_MAX_CODES = 7000  # keep the asset list inside a sane URL length
_TIMEOUT = 120  # seconds per HTTP call
_MIN_INTERVAL = 1.0  # seconds between request starts → 60/min, below the 100/min data limit
_MAX_ATTEMPTS = 5
_BACKOFF_BASE = 2.0  # retry waits ≈2, 4, 8, 16 s (+ jitter, or Retry-After when larger)
RAW_COLS = ["permid", "date", "source", "buzz", "sentiment"]

_last_request = 0.0


def api_key() -> str:
    """Read the pull API key from .env (never logged, echoed or written to a file)."""
    load_dotenv()
    key = os.getenv(_ENV_VAR)
    if not key:
        raise RuntimeError(f"{_ENV_VAR} missing from .env")
    return key


def month_windows(start: str, end: str) -> list[tuple[str, str]]:
    """Calendar-month [start, end) windows covering [start, end), clipped at both ends."""
    first = cast(pd.Timestamp, pd.Timestamp(start))  # malformed dates raise; never NaT
    last = cast(pd.Timestamp, pd.Timestamp(end))
    if first >= last:
        return []
    bounds = [
        first,
        *pd.date_range(first, last, freq="MS", inclusive="neither").tolist(),
        last,
    ]
    return [(f"{a:%Y-%m-%d}", f"{b:%Y-%m-%d}") for a, b in zip(bounds, bounds[1:])]


def _throttle() -> None:
    """Client-side pacing: at least _MIN_INTERVAL between request starts."""
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request = time.monotonic()


def http_get(url: str) -> bytes:
    """GET a data URL, retrying throttles and 5xx; the URL carries the key, never log it."""
    _throttle()
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return urllib.request.urlopen(url, timeout=_TIMEOUT).read()
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


def normalize_pull(df: pd.DataFrame) -> pd.DataFrame:
    """Rename the pull response to RAW_COLS; normalize permid, date and source."""
    out = df.rename(
        columns={"assetCode": "permid", "windowTimestamp": "date", "dataType": "source"}
    )
    out["permid"] = out["permid"].astype(str)
    out["date"] = pd.to_datetime(out["date"], utc=True).dt.tz_convert(None).dt.normalize()
    out["source"] = out["source"].str.lower()
    return out.reindex(columns=RAW_COLS).drop_duplicates(subset=["permid", "date", "source"])


def fetch_marketpsych(cfg: dict[str, Any]) -> None:
    """Cache one parquet slice per calendar month from the MarketPsych pull API.

    Reads: <universe.assets_out>
    Writes: one <marketpsych.raw_out>/YYYY-MM.parquet per month
    """
    assets_path = Path(cfg["universe"]["assets_out"])
    if not assets_path.exists():
        raise FileNotFoundError(f"run the universe step first; missing: {assets_path}")
    permids = sorted(
        pd.read_parquet(assets_path, columns=["permid"])["permid"].astype(str).unique()
    )
    codes = ",".join(permids)
    if len(permids) * 31 > _MAX_ASSET_DAYS:
        raise RuntimeError(f"too many assets for one pull query: {len(permids)}")
    if len(codes) > _MAX_CODES:
        raise RuntimeError(f"asset code list too long for one URL: {len(codes)} codes")

    mp = cfg["marketpsych"]
    cache_dir = Path(mp["raw_out"])
    pending = []
    for start, end in month_windows(mp["start"], mp["end"]):
        path = store.cache_path(cache_dir, start[:7])
        if not path.exists() or cfg.get("_refresh"):
            pending.append((start, end, path))
    if not pending:
        log.info("marketpsych: all month caches present in %s", cache_dir)
        return

    key = api_key()  # only needed when there is real work
    base = f"{_ENTRY}/{mp['asset_class']}/{mp['frequency']}/{codes}"
    datatypes = ",".join(mp["datatypes"])
    datacols = ",".join(mp["datacols"])
    for start, end, path in pending:
        query = urllib.parse.urlencode(
            {
                "apikey": key,
                "start_date": start,
                "end_date": end,
                "datatype": datatypes,
                "datacols": datacols,
                "format": "csv",
            },
            safe=",",
        )
        body = http_get(f"{base}?{query}")
        df = (
            pd.read_csv(io.BytesIO(body))
            if body.strip()
            else pd.DataFrame(columns=pd.Index(RAW_COLS))
        )
        store.write_parquet(normalize_pull(df), path)
        log.info("wrote %s (%d rows)", path, len(df))
    log.info("marketpsych: %d month caches in %s", len(pending), cache_dir)
