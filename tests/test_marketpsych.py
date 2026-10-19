"""Synthetic checks for the MarketPsych fetch/build chain (no network)."""

import io
import json
import urllib.error
import urllib.request
import zipfile
from email.message import Message
from pathlib import Path

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


def _reference(*rows) -> bytes:
    return json.dumps({"data": list(rows)}).encode()


def _write_reference(path, rows=()):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "permid": str(row["assetCode"]),
                "name": row.get("name"),
                "ric": row.get("RIC"),
                "ticker": row.get("Ticker"),
                "status": row.get("status", "active"),
                "current_permid": str(row.get("CurrentInstrumentIssuerPermid") or row["assetCode"]),
            }
            for row in rows
        ],
        columns=["permid", "name", "ric", "ticker", "status", "current_permid"],
    ).to_parquet(path, index=False)


def _cfg(tmp_path, assets_path, raw_dir, start="1998-01-01", end="1998-03-01"):
    reference = Path(raw_dir) / "reference" / "assets.parquet"
    if not reference.exists():
        _write_reference(reference)  # empty map: fetch tests never need a reference request
    return {
        "universe": {"assets_out": str(assets_path)},
        "marketpsych": {
            "start": start,
            "end": end,
            "asset_classes": ["equamer"],
            "frequency": "dai",
            "datatypes": ["News_Social"],
            "datacols": ["buzz", "sentiment"],
            "reference_out": str(reference),
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
    """Stub `_open`: listing URLs serve `listing` (a body, or per asset class when given a
    dict keyed by class), payload links serve `payloads` by name."""
    calls: list[str] = []

    def fake_open(url, offset=0):
        if url.startswith(marketpsych._BASE):
            calls.append("listing")
            body = (
                listing[url.split("/files/", 1)[1].split("/", 1)[0]]
                if isinstance(listing, dict)
                else listing
            )
            return _Response(body)
        name = url.split("?")[0].rsplit("/", 1)[-1]
        calls.append(name)
        return _Response(payloads[name])

    monkeypatch.setattr(marketpsych, "api_key", lambda: "SECRET")
    monkeypatch.setattr(marketpsych, "_open", fake_open)
    return calls


def _patch_reference(monkeypatch, rows=()):
    """Stub the asset reference request (its own opener, not the listing/payload one)."""
    monkeypatch.setattr(marketpsych, "_open_reference", lambda url: _Response(_reference(*rows)))


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
    _patch_reference(monkeypatch)  # --refresh refetches the reference too

    cfg = _cfg(tmp_path, assets_path, raw_dir)
    cfg["_refresh"] = True
    marketpsych.fetch_marketpsych(cfg)

    assert calls == ["listing"]  # the payload is kept, only its slice is rewritten
    out = pd.read_parquet(store.cache_path(raw_dir, _LIVE))
    assert out["buzz"].tolist() == [3.0]


def test_fetch_lists_each_asset_class(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["SHEL.N"], "permid": ["4295885039"]}).to_parquet(assets_path, index=False)
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    emea = "PRO.Archive.CMPNY_EMEA.WDAI_UDAI.199802.0400.zip"
    blob = _tsv([_row("a", 4295885039, "News_Social", 3.0, 0.25)])
    calls = _patch_open(
        monkeypatch,
        {"equamer": _listing(_ARCHIVE), "equemea": _listing(emea)},
        {_ARCHIVE: _zip("payload.txt", _tsv([])), emea: _zip("payload.txt", blob)},
    )
    cfg = _cfg(tmp_path, assets_path, raw_dir)
    cfg["marketpsych"]["asset_classes"] = ["equamer", "equemea"]

    marketpsych.fetch_marketpsych(cfg)

    assert calls.count("listing") == 2  # one listing per class
    out = pd.read_parquet(store.cache_path(raw_dir, emea))
    assert out["permid"].tolist() == ["4295885039"]
    assert out["buzz"].tolist() == [3.0]


def test_fetch_uses_reference_successor_link(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["TSLA.OQ"], "permid": ["222"]}).to_parquet(assets_path, index=False)
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    blob = _tsv([_row("a", 111, "News_Social", 3.0, 0.25)])
    _patch_open(monkeypatch, _listing(_ARCHIVE), {_ARCHIVE: _zip("payload.txt", blob)})
    cfg = _cfg(tmp_path, assets_path, raw_dir)
    _write_reference(
        cfg["marketpsych"]["reference_out"],
        [{"assetCode": 111, "CurrentInstrumentIssuerPermid": 222}],
    )

    marketpsych.fetch_marketpsych(cfg)

    out = pd.read_parquet(store.cache_path(raw_dir, _ARCHIVE))
    assert out["permid"].tolist() == ["222"]  # old code re-keyed to the current company
    assert out["buzz"].tolist() == [3.0]


def test_fetch_does_not_rewrite_live_universe_permid(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["HON.OQ", "MDT.N"], "permid": ["111", "222"]}).to_parquet(
        assets_path, index=False
    )
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    blob = _tsv([_row("a", 111, "News_Social", 3.0, 0.25)])
    _patch_open(monkeypatch, _listing(_ARCHIVE), {_ARCHIVE: _zip("payload.txt", blob)})
    cfg = _cfg(tmp_path, assets_path, raw_dir)
    _write_reference(
        cfg["marketpsych"]["reference_out"],
        [{"assetCode": 111, "CurrentInstrumentIssuerPermid": 222}],
    )

    marketpsych.fetch_marketpsych(cfg)

    out = pd.read_parquet(store.cache_path(raw_dir, _ARCHIVE))
    assert out["permid"].tolist() == ["111"]  # both ids are live: no rewrite, row survives


def test_fetch_entity_override_replaces_permid_series(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["LIN.OQ"], "permid": ["222"]}).to_parquet(assets_path, index=False)
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    blob = _tsv(
        [
            _row("a", 111, "News_Social", 3.0, 0.25),
            _row("b", 222, "News_Social", 5.0, 0.10),
        ]
    )
    _patch_open(monkeypatch, _listing(_ARCHIVE), {_ARCHIVE: _zip("payload.txt", blob)})
    cfg = _cfg(tmp_path, assets_path, raw_dir)
    cfg["marketpsych"]["entity_overrides"] = {"222": "111"}

    marketpsych.fetch_marketpsych(cfg)

    out = pd.read_parquet(store.cache_path(raw_dir, _ARCHIVE))
    assert out["permid"].tolist() == ["222"]  # override row re-keyed, native row dropped
    assert out["buzz"].tolist() == [3.0]


def test_entity_override_rejects_universe_permid():
    with pytest.raises(ValueError, match="is a universe PermID"):
        marketpsych.apply_overrides({}, {"1", "2"}, {"1": "2"})


def test_fetch_links_xom_by_normalized_name(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["XOM.N"], "permid": ["6000179751"]}).to_parquet(assets_path, index=False)
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    blob = _tsv([_row("a", 4295912121, "News_Social", 3.0, 0.25)])
    _patch_open(monkeypatch, _listing(_ARCHIVE), {_ARCHIVE: _zip("payload.txt", blob)})
    cfg = _cfg(tmp_path, assets_path, raw_dir)
    _write_reference(
        cfg["marketpsych"]["reference_out"],
        [
            {
                "assetCode": 6000179751,
                "name": "Exxonmobil Holdings Corp",
                "RIC": "XOM.N",
                "Ticker": "XOM",
            },
            {"assetCode": 4295912121, "name": "Exxon Mobil Corporation"},  # no RIC/ticker
        ],
    )

    marketpsych.fetch_marketpsych(cfg)

    out = pd.read_parquet(store.cache_path(raw_dir, _ARCHIVE))
    assert out["permid"].tolist() == ["6000179751"]  # name fallback, no manual alias
    assert out["buzz"].tolist() == [3.0]


def test_fetch_fetches_reference_and_reparses_on_first_run(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["TSLA.OQ"], "permid": ["222"]}).to_parquet(assets_path, index=False)
    raw_dir = tmp_path / "mp"
    payload = raw_dir / "files" / _ARCHIVE
    payload.parent.mkdir(parents=True)
    blob = _tsv([_row("a", 111, "News_Social", 3.0, 0.25)])
    payload.write_bytes(_zip("payload.txt", blob))
    _slice(store.cache_path(raw_dir, _ARCHIVE), ["1998-01-05"], [9.0], permid="222")  # stale
    _patch_open(monkeypatch, _listing(_ARCHIVE), {})  # a payload download would KeyError
    _patch_reference(
        monkeypatch,
        [
            {"assetCode": 111, "CurrentInstrumentIssuerPermid": 222},
            {"assetCode": 555, "CurrentInstrumentIssuerPermid": None},  # forces a nullable column
        ],
    )
    cfg = _cfg(tmp_path, assets_path, raw_dir)
    reference_path = Path(cfg["marketpsych"]["reference_out"])
    reference_path.unlink()  # first run after the upgrade: no cached reference

    marketpsych.fetch_marketpsych(cfg)

    assert reference_path.exists()
    out = pd.read_parquet(store.cache_path(raw_dir, _ARCHIVE))
    assert out["permid"].tolist() == ["222"]  # re-parsed from the kept payload
    assert out["buzz"].tolist() == [3.0]  # the stale slice is gone


def test_fetch_skips_reference_fetch_when_cached(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["AAPL.OQ"], "permid": ["4295905573"]}).to_parquet(
        assets_path, index=False
    )
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    blob = _tsv([_row("a", 4295905573, "News_Social", 3.0, 0.25)])
    _patch_open(monkeypatch, _listing(_LIVE), {_LIVE: blob})
    cfg = _cfg(tmp_path, assets_path, raw_dir)  # _cfg writes the reference cache
    monkeypatch.setattr(
        marketpsych, "_open_reference", lambda url: pytest.fail("reference refetched")
    )

    marketpsych.fetch_marketpsych(cfg)

    out = pd.read_parquet(store.cache_path(raw_dir, _LIVE))
    assert out["buzz"].tolist() == [3.0]


def test_build_aliases_drops_ambiguous_successor_links():
    assets = pd.DataFrame({"permid": ["222", "333"]})
    reference = pd.DataFrame(
        {
            "permid": ["111", "111"],
            "name": ["Old Co", "Old Co"],
            "ric": [None, None],
            "ticker": [None, None],
            "status": ["inactive", "inactive"],
            "current_permid": ["222", "333"],  # one old code, two current companies
        }
    )

    assert marketpsych.build_aliases(assets, reference) == {}


def test_build_aliases_skips_ambiguous_name_keys():
    assets = pd.DataFrame({"permid": ["222", "333"]})
    reference = pd.DataFrame(
        {
            "permid": ["222", "333", "444"],
            "name": ["Acme Corp", "Acme Incorporated", "Acme"],  # both normalize to "acme"
            "ric": ["A.N", "B.N", None],
            "ticker": ["A", "B", None],
            "status": ["active"] * 3,
            "current_permid": ["222", "333", "444"],
        }
    )

    assert marketpsych.build_aliases(assets, reference) == {}


def test_read_slice_rejects_unknown_columns(tmp_path):
    payload = tmp_path / "payload.txt"
    payload.write_bytes(
        b"assetCode\twindowTimestamp\tdataType\tsentiment\n1\tx\tNews_Social\t0.1\n"
    )
    with pytest.raises(RuntimeError, match="buzz"):
        marketpsych.read_slice(payload, pd.Index(["1"]), {"news_social"}, ["buzz", "sentiment"], {})


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
