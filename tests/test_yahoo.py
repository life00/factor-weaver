"""Synthetic checks for Yahoo normalization, caching and the market step (no network)."""

import pandas as pd

from factor_weaver.data import yahoo

_COLS = ["date", "symbol", "open", "high", "low", "close", "volume"]


def test_resolve_symbol_override_wins_over_ticker():
    cfg = {"yahoo": {"symbol_overrides": {"A.N": "AA"}}}
    assert yahoo.resolve_symbol(cfg, "A.N", "A") == "AA"
    assert yahoo.resolve_symbol(cfg, "B.N", "B") == "B"
    assert yahoo.resolve_symbol({}, "B.N", "B") == "B"


def test_normalize_tz_aware_history():
    idx = pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-03"]), name="Date").tz_localize(
        "America/New_York"
    )
    raw = pd.DataFrame(
        {
            "Open": [1.0, 2.0],
            "High": [1.5, 2.5],
            "Low": [0.5, 1.5],
            "Close": [1.2, 2.2],
            "Volume": [100, 200],
            "Dividends": [0.0, 0.0],
        },
        index=idx,
    )
    out = yahoo._normalize(raw, "^GSPC")
    assert list(out.columns) == _COLS
    assert out["date"].dt.tz is None
    assert list(out["date"]) == [pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-03")]
    assert set(out["symbol"]) == {"^GSPC"}


def test_normalize_empty_is_canonical_empty():
    out = yahoo._normalize(pd.DataFrame(), "ENE")
    assert out.empty
    assert list(out.columns) == _COLS


def _one_day(symbol):
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2020-01-02")],
            "symbol": [symbol],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [0],
        }
    )


def test_fetch_symbols_caches_and_reuses(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(symbol, start, end):
        calls.append(symbol)
        return _one_day(symbol)

    monkeypatch.setattr(yahoo, "_fetch_symbol", fake_fetch)
    cfg = {"yahoo": {"prices_out": tmp_path / "cache"}}
    out = yahoo.fetch_symbols(cfg, ["^VIX", "ENE"], "2020-01-01", "2020-01-31")
    assert set(out["symbol"]) == {"^VIX", "ENE"}
    assert (tmp_path / "cache" / "^VIX.parquet").exists()
    yahoo.fetch_symbols(cfg, ["^VIX"], "2020-01-01", "2020-01-31")
    assert calls == ["^VIX", "ENE"]  # second run served from cache


def test_fetch_symbols_empty_is_canonical_empty(tmp_path):
    out = yahoo.fetch_symbols({"yahoo": {"prices_out": tmp_path}}, [], "2020-01-01", "2020-01-02")
    assert out.empty
    assert list(out.columns) == _COLS


def test_write_extra_prices_filters_and_writes(tmp_path):
    raw = pd.concat([_one_day("^VIX"), _one_day("ENE")], ignore_index=True)
    cfg = {
        "yahoo": {
            "extra_prices_out": tmp_path / "extra_prices.parquet",
            "extra_symbols": ["^VIX"],
        }
    }
    yahoo.write_extra_prices(cfg, raw)
    out = pd.read_parquet(tmp_path / "extra_prices.parquet")
    assert set(out["symbol"]) == {"^VIX"}
