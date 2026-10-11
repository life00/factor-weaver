"""Synthetic checks for the MarketPsych fetch/build chain (no network)."""

import io
import urllib.error
import urllib.request
from email.message import Message

import pandas as pd
import pytest

from factor_weaver.data.build.behavioral import OUT_COLS, build_behavioral
from factor_weaver.data.fetch import marketpsych

_CSV = (
    b"assetCode,windowTimestamp,dataType,buzz,sentiment\n"
    b"4295905573,1998-02-03T20:30:00+00:00,News_Social,3.0,0.25\n"
)


def _cfg(tmp_path, assets_path, raw_dir, start="1998-01-01", end="1998-03-01"):
    return {
        "universe": {"assets_out": str(assets_path)},
        "marketpsych": {
            "start": start,
            "end": end,
            "asset_class": "equ",
            "frequency": "dai",
            "datatypes": ["News_Social"],
            "datacols": ["buzz", "sentiment"],
            "raw_out": str(raw_dir),
            "out": str(tmp_path / "behavioral.parquet"),
        },
    }


def test_month_windows_clips_to_bounds():
    assert marketpsych.month_windows("1998-01-15", "1998-04-01") == [
        ("1998-01-15", "1998-02-01"),
        ("1998-02-01", "1998-03-01"),
        ("1998-03-01", "1998-04-01"),
    ]


def test_normalize_pull_renames_types_and_dedups():
    row = {
        "id": ["abc"],
        "assetCode": [4295905573],
        "ticker": ["AAPL.O"],
        "windowTimestamp": ["2022-02-03T20:30:00+00:00"],
        "dataType": ["News_Social"],
        "buzz": [3.5],
        "sentiment": [0.4],
    }
    out = marketpsych.normalize_pull(pd.DataFrame(row).loc[[0, 0]].reset_index(drop=True))
    assert list(out.columns) == marketpsych.RAW_COLS
    assert out["permid"].tolist() == ["4295905573"]
    assert out["date"].tolist() == [pd.Timestamp("2022-02-03")]
    assert out["date"].dt.tz is None
    assert out["source"].tolist() == ["news_social"]
    assert out["buzz"].tolist() == [3.5]


def test_fetch_skips_cached_months_and_writes_slices(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["AAPL.OQ"], "permid": ["4295905573"]}).to_parquet(
        assets_path, index=False
    )
    raw_dir = tmp_path / "mp"
    raw_dir.mkdir()
    pd.DataFrame(
        {
            "permid": ["4295905573"],
            "date": pd.to_datetime(["1998-01-02"]),
            "source": ["news_social"],
            "buzz": [1.0],
            "sentiment": [0.5],
        }
    ).to_parquet(raw_dir / "1998-01.parquet", index=False)

    calls: list[str] = []

    def fake_get(url):
        calls.append(url)
        return _CSV

    monkeypatch.setattr(marketpsych, "http_get", fake_get)
    marketpsych.fetch_marketpsych(_cfg(tmp_path, assets_path, raw_dir))

    assert len(calls) == 1  # January is cached, only February is requested
    url = calls[0]
    assert "/data/equ/dai/" in url
    assert "datatype=News_Social" in url
    assert "datacols=buzz,sentiment" in url
    assert "start_date=1998-02-01" in url and "end_date=1998-03-01" in url
    out = pd.read_parquet(raw_dir / "1998-02.parquet")
    assert out["permid"].tolist() == ["4295905573"]
    assert out["date"].tolist() == [pd.Timestamp("1998-02-03")]


def test_http_get_raises_api_error_body(monkeypatch):
    attempts: list[str] = []

    def fake_urlopen(url, timeout=None):
        attempts.append(url)
        raise urllib.error.HTTPError(
            url, 401, "Unauthorized", Message(), io.BytesIO(b'{"error":"Invalid/expired api key"}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError) as excinfo:
        marketpsych.http_get("https://dataapi.marketpsych.com/rma/v4/data?apikey=SECRETKEY")
    msg = str(excinfo.value)
    assert "marketpsych api error 401" in msg
    assert "Invalid/expired api key" in msg
    assert "SECRETKEY" not in msg
    assert len(attempts) == 1  # 4xx is a config error, not worth retrying


def test_http_get_retries_429_with_retry_after_and_paces_requests(monkeypatch):
    url = "https://dataapi.marketpsych.com/rma/v4/data?apikey=SECRETKEY"
    clock = [100.0]
    waits: list[float] = []
    calls: list[str] = []

    class _Stub:
        def read(self):
            return _CSV

    def fake_urlopen(target, timeout=None):
        calls.append(target)
        if len(calls) == 1:
            headers = Message()
            headers["Retry-After"] = "3"
            raise urllib.error.HTTPError(
                target, 429, "Too Many Requests", headers, io.BytesIO(b"rate limited")
            )
        return _Stub()

    def fake_sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(marketpsych, "_last_request", 0.0)
    monkeypatch.setattr(marketpsych.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(marketpsych.time, "sleep", fake_sleep)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert marketpsych.http_get(url).startswith(b"assetCode")
    assert len(calls) == 2  # 429 then success
    assert waits == [3.0]  # Retry-After (3 s) wins over the 2 s backoff base

    clock[0] = marketpsych._last_request  # two requests with no time in between
    waits.clear()
    marketpsych.http_get(url)
    assert waits == [marketpsych._MIN_INTERVAL]  # client-side pacing


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
