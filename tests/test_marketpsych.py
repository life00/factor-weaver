"""Synthetic checks for the MarketPsych fetch/build chain (no network)."""

import io
import json
import urllib.error
import urllib.request
import zipfile
from email.message import Message

import pandas as pd
import pytest

from factor_weaver.data import store
from factor_weaver.data.build.behavioral import OUT_COLS, build_behavioral
from factor_weaver.data.fetch import marketpsych

_HEADER = (
    "id\tassetCode\tticker\twindowTimestamp\tdataType\tsystemVersion"
    "\tmentions\tbuzz\tsentiment\tfear"
)
_ARCHIVE = "PRO.Archive.CMPNY_AMER.WDAI_UDAI.199802.0400.zip"
_LIVE = "PRO.Live.CMPNY_AMER.WDAI_UDAI.19980203.0400.txt"


def _listing(*names):
    files = [
        {
            "filename": name,
            "link": f"https://files.marketpsychdata.com/PRO/MI4/CMPNY_AMER/WDAI_UDAI/{name}"
            "?md5=0123456789abcdef0123456789abcdef&expires=1",
            "size": 1000 + i,
            "date_modified": "2026-10-12T00:00:00Z",
        }
        for i, name in enumerate(names)
    ]
    return json.dumps({"data": files}).encode()


def _tsv(rows):
    lines = [_HEADER]
    lines.extend("\t".join(str(cell) for cell in row) for row in rows)
    return ("\n".join(lines) + "\n").encode()


def _zip(member, blob):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, blob)
    return buffer.getvalue()


def _row(key, permid, datatype, buzz, sentiment, timestamp="1998-02-03T20:30:00+00:00"):
    return [key, permid, "AAPL.O", timestamp, datatype, "4.5", 1, buzz, sentiment, 0.1]


class _Response(io.BytesIO):
    """urlopen stand-in: body bytes plus the HTTP status `download` inspects."""

    def __init__(self, blob, status=200):
        super().__init__(blob)
        self.status = status


class _Reset(_Response):
    """A response that hands over `cut` bytes and then the connection drops."""

    def __init__(self, blob, cut, status=200):
        super().__init__(blob[:cut], status)
        self._reads = 0

    def read(self, n=-1):
        if self._reads:
            raise ConnectionResetError(104, "Connection reset by peer")
        self._reads += 1
        return super().read(n)


def _slice(path, dates, buzz, permid="5030853586"):
    pd.DataFrame(
        {
            "permid": [permid] * len(dates),
            "date": pd.to_datetime(dates),
            "source": ["news_social"] * len(dates),
            "buzz": buzz,
            "sentiment": [0.1] * len(dates),
        }
    ).to_parquet(path, index=False)


def _cfg(tmp_path, assets_path, raw_dir, start="1998-01-01", end="1998-03-01"):
    return {
        "universe": {"assets_out": str(assets_path)},
        "marketpsych": {
            "start": start,
            "end": end,
            "asset_class": "equamer",
            "frequency": "dai",
            "datatypes": ["News_Social"],
            "datacols": ["buzz", "sentiment"],
            "raw_out": str(raw_dir),
            "out": str(tmp_path / "behavioral.parquet"),
        },
    }


def test_list_files_builds_url_and_parses_entries(monkeypatch):
    urls: list[str] = []
    listing = _listing(_ARCHIVE, _LIVE)

    def fake_open(url, offset=0):
        urls.append(url)
        return _Response(listing)

    monkeypatch.setattr(marketpsych, "api_key", lambda: "SECRET")
    monkeypatch.setattr(marketpsych, "_open", fake_open)

    entries = marketpsych.list_files("equamer", "dai", "1998-01-01", "1998-03-01")

    assert urls == [
        "https://dataapi.marketpsych.com/rma/v4/files/equamer/dai"
        "?apikey=SECRET&start_date=1998-01-01&end_date=1998-03-01"
    ]
    assert [e["filename"] for e in entries] == [_ARCHIVE, _LIVE]
    assert entries[0]["size"] == 1000


def _patch_open(monkeypatch, listing, payloads):
    """Stub `_open`: the listing URL serves `listing`, payload links serve `payloads` by name."""
    calls: list[str] = []

    def fake_open(url, offset=0):
        if url.startswith(marketpsych._BASE):
            calls.append("listing")
            return _Response(listing)
        name = url.split("?")[0].rsplit("/", 1)[-1]
        calls.append(name)
        return _Response(payloads[name])

    monkeypatch.setattr(marketpsych, "api_key", lambda: "SECRET")
    monkeypatch.setattr(marketpsych, "_open", fake_open)
    return calls


def test_fetch_writes_slice_per_listed_file_and_skips_cached(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["AAPL.OQ"], "permid": ["4295905573"]}).to_parquet(
        assets_path, index=False
    )
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    cached = "PRO.Archive.CMPNY_AMER.WDAI_UDAI.199711.0400.zip"
    _slice(store.cache_path(raw_dir, cached), ["1997-11-03"], [1.0], permid="4295905573")
    blob = _tsv(
        [
            _row("a", 4295905573, "News_Social", 3.0, 0.25),
            _row("b", 4295905573, "News", 5.0, 0.10, timestamp="1998-02-04T20:30:00+00:00"),
            _row("c", 999, "News_Social", 2.0, 0.10, timestamp="1998-02-04T20:30:00+00:00"),
        ]
    )
    calls = _patch_open(
        monkeypatch,
        _listing(_ARCHIVE, _LIVE, cached),
        {_ARCHIVE: _zip("payload.txt", blob), _LIVE: blob},
    )

    marketpsych.fetch_marketpsych(_cfg(tmp_path, assets_path, raw_dir))

    assert sorted(n for n in calls if n != "listing") == [_ARCHIVE, _LIVE]  # cached slice skipped
    assert (raw_dir / "files" / _ARCHIVE).exists()
    assert (raw_dir / "files" / _LIVE).exists()
    for name in (_ARCHIVE, _LIVE):
        out = pd.read_parquet(store.cache_path(raw_dir, name))
        assert list(out.columns) == marketpsych.RAW_COLS
        assert out["permid"].tolist() == ["4295905573"]  # non-universe PermID dropped
        assert out["source"].tolist() == ["news_social"]  # non-News_Social row dropped
        assert out["date"].dt.tz is None
        assert out["date"].tolist() == [pd.Timestamp("1998-02-03")]
        assert out["buzz"].tolist() == [3.0]


def test_fetch_refresh_reparses_without_redownloading(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["AAPL.OQ"], "permid": ["4295905573"]}).to_parquet(
        assets_path, index=False
    )
    raw_dir = tmp_path / "mp"
    payload = raw_dir / "files" / _LIVE
    payload.parent.mkdir(parents=True)
    payload.write_bytes(_tsv([_row("a", 4295905573, "News_Social", 3.0, 0.25)]))
    calls = _patch_open(monkeypatch, _listing(_LIVE), {})

    cfg = _cfg(tmp_path, assets_path, raw_dir)
    cfg["_refresh"] = True
    marketpsych.fetch_marketpsych(cfg)

    assert calls == ["listing"]  # the payload is kept, only its slice is rewritten
    out = pd.read_parquet(store.cache_path(raw_dir, _LIVE))
    assert out["buzz"].tolist() == [3.0]


def test_read_slice_rejects_unknown_columns(tmp_path):
    payload = tmp_path / "payload.txt"
    payload.write_bytes(b"assetCode\twindowTimestamp\tdataType\tsentiment\n1\tx\tNews_Social\t0.1\n")
    with pytest.raises(RuntimeError, match="buzz"):
        marketpsych.read_slice(payload, pd.Index(["1"]), {"news_social"}, ["buzz", "sentiment"])


def test_list_files_raises_api_error_body_without_leaking_key(monkeypatch):
    attempts: list[str] = []

    def fake_urlopen(request, timeout=None):
        attempts.append(request.get_full_url())
        raise urllib.error.HTTPError(
            request.get_full_url(),
            401,
            "Unauthorized",
            Message(),
            io.BytesIO(b'{"error":"Invalid/expired api key"}'),
        )

    monkeypatch.setattr(marketpsych, "api_key", lambda: "SECRETKEY")
    monkeypatch.setattr(marketpsych, "_last_request", 0.0)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError) as excinfo:
        marketpsych.list_files("equamer", "dai", "1998-01-01", "1998-03-01")
    msg = str(excinfo.value)
    assert "http 401" in msg
    assert "Invalid/expired api key" in msg
    assert "SECRETKEY" not in msg
    assert len(attempts) == 1  # 4xx is a config error, not worth retrying


def test_list_files_retries_429_with_retry_after_and_paces_requests(monkeypatch):
    clock = [100.0]
    waits: list[float] = []
    calls: list[str] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.get_full_url())
        if len(calls) == 1:
            headers = Message()
            headers["Retry-After"] = "3"
            raise urllib.error.HTTPError(
                request.get_full_url(),
                429,
                "Too Many Requests",
                headers,
                io.BytesIO(b"rate limited"),
            )
        return _Response(_listing(_ARCHIVE))

    def fake_sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(marketpsych, "api_key", lambda: "SECRET")
    monkeypatch.setattr(marketpsych, "_last_request", 0.0)
    monkeypatch.setattr(marketpsych.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(marketpsych.time, "sleep", fake_sleep)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    entries = marketpsych.list_files("equamer", "dai", "1998-01-01", "1998-03-01")
    assert [e["filename"] for e in entries] == [_ARCHIVE]
    assert len(calls) == 2  # 429 then success
    assert waits == [3.0]  # Retry-After (3 s) wins over the 2 s backoff base

    clock[0] = marketpsych._last_request  # two requests with no time in between
    waits.clear()
    marketpsych.list_files("equamer", "dai", "1998-01-01", "1998-03-01")
    assert waits == [marketpsych._MIN_INTERVAL]  # client-side pacing


def test_download_resumes_after_reset_with_range(tmp_path, monkeypatch):
    blob = b"x" * (200 * 1024)  # more than one copyfileobj chunk
    ranges: list[str | None] = []

    def fake_urlopen(request, timeout=None):
        header = request.get_header("Range")
        ranges.append(header)
        if header is None:
            return _Reset(blob, 64 * 1024)  # the first chunk lands, then the reset
        return _Response(blob[int(header[6:-1]) :], status=206)

    monkeypatch.setattr(marketpsych, "_last_request", 0.0)
    monkeypatch.setattr(marketpsych.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    path = tmp_path / "payload.zip"
    marketpsych.download("https://files.marketpsychdata.com/PRO/x.zip?md5=0&expires=1", path)

    assert ranges == [None, "bytes=65536-"]  # the retry asks for the rest, not the whole file
    assert path.read_bytes() == blob
    assert not path.with_name(path.name + ".tmp").exists()


def test_build_behavioral_broadcasts_permid_to_each_ric(tmp_path):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame(
        {
            "ric": ["GOOG.OQ", "GOOGL.OQ", "MSFT.OQ"],
            "permid": ["5030853586", "5030853586", "1111111111"],
        }
    ).to_parquet(assets_path, index=False)
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    pd.DataFrame(
        {
            "permid": ["5030853586", "5030853586"],
            "date": pd.to_datetime(["2022-02-03", "2022-02-04"]),
            "source": ["news_social", "news_social"],
            "buzz": [3.0, 4.0],
            "sentiment": [0.2, -0.1],
        }
    ).to_parquet(raw_dir / "2022-02.parquet", index=False)

    cfg = _cfg(tmp_path, assets_path, raw_dir, start="2022-02-01", end="2022-03-01")
    build_behavioral(cfg)
    out = pd.read_parquet(cfg["marketpsych"]["out"])
    assert list(out.columns) == OUT_COLS
    assert len(out) == 4  # 2 RICs × 2 dates
    assert set(out["ric"]) == {"GOOG.OQ", "GOOGL.OQ"}
    got = out.sort_values("date").groupby("ric")["buzz"].apply(tuple)
    assert got.to_dict() == {"GOOG.OQ": (3.0, 4.0), "GOOGL.OQ": (3.0, 4.0)}


def test_build_behavioral_prefers_archive_slice_over_live(tmp_path):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["GOOG.OQ"], "permid": ["5030853586"]}).to_parquet(
        assets_path, index=False
    )
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    _slice(store.cache_path(raw_dir, _LIVE), ["1998-02-03"], [9.0])
    _slice(store.cache_path(raw_dir, _ARCHIVE), ["1998-02-03"], [1.0])

    cfg = _cfg(tmp_path, assets_path, raw_dir, start="1998-02-01", end="1998-03-01")
    build_behavioral(cfg)
    out = pd.read_parquet(cfg["marketpsych"]["out"])
    assert out["buzz"].tolist() == [1.0]  # the archive row supersedes the live slice


def test_build_behavioral_clips_to_configured_window(tmp_path):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["GOOG.OQ"], "permid": ["5030853586"]}).to_parquet(
        assets_path, index=False
    )
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    _slice(store.cache_path(raw_dir, _ARCHIVE), ["1998-01-15", "1998-02-10"], [1.0, 2.0])

    cfg = _cfg(tmp_path, assets_path, raw_dir, start="1998-02-01", end="1998-03-01")
    build_behavioral(cfg)
    out = pd.read_parquet(cfg["marketpsych"]["out"])
    assert out["date"].tolist() == [pd.Timestamp("1998-02-10")]  # the archive covers all of January
