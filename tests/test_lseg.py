"""Synthetic checks for LSEG price normalization (no API calls)."""

import pandas as pd

from factor_weaver.data.fetch.lseg import _normalize_history, fetch_history, resolve_ric

_FIELDS = {
    "OPEN_PRC": [1.0, 2.0],
    "HIGH_1": [1.5, 2.5],
    "LOW_1": [0.5, 1.5],
    "TRDPRC_1": [1.2, 2.2],
    "ACVOL_UNS": [100, 200],
}


def test_normalize_columns_dates_and_ric():
    idx = pd.DatetimeIndex(pd.to_datetime(["2020-08-31", "2020-08-28"], utc=True), name="Date")
    out = _normalize_history(pd.DataFrame(_FIELDS, index=idx), "AAPL.O")
    assert list(out.columns) == ["date", "ric", "open", "high", "low", "close", "volume"]
    assert out["date"].dt.tz is None
    assert list(out["date"]) == [pd.Timestamp("2020-08-28"), pd.Timestamp("2020-08-31")]
    assert set(out["ric"]) == {"AAPL.O"}


def test_normalize_empty_response_is_empty_not_error():
    out = _normalize_history(pd.DataFrame(), "ENE.N^A02")
    assert out.empty
    assert list(out.columns) == ["date", "ric", "open", "high", "low", "close", "volume"]


def test_normalize_drops_empty_rows_and_fills_missing_fields():
    idx = pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-03"], utc=True), name="Date")
    raw = pd.DataFrame({k: v for k, v in _FIELDS.items() if k != "ACVOL_UNS"}, index=idx)
    raw.loc[idx[1], "TRDPRC_1"] = None
    out = _normalize_history(raw, ".SPX")
    assert len(out) == 1
    assert out["close"].iloc[0] == 1.2
    assert out["volume"].isna().all()


class _FakeLD:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def get_history(self, universe, **kwargs):
        self.calls.append(universe)
        if universe not in self.frames:
            raise RuntimeError(f"{universe}: no data")
        return self.frames[universe]


def _one_day_frame():
    idx = pd.DatetimeIndex(pd.to_datetime(["2020-01-02"], utc=True), name="Date")
    return pd.DataFrame({k: [1.0] for k in _FIELDS}, index=idx)


def test_resolve_ric_uses_fallback_only_when_mapped():
    cfg = {"lseg": {"ric_fallbacks": {"KHC.OQ": "KHC.N"}}}
    assert resolve_ric(cfg, "KHC.OQ") == "KHC.N"
    assert resolve_ric(cfg, "AAPL.O") == "AAPL.O"
    assert resolve_ric({}, "AAPL.O") == "AAPL.O"


def test_fetch_history_queries_retired_rics_and_normalizes():
    ld = _FakeLD({"TWX.N^A01": _one_day_frame()})
    out = fetch_history(ld, "TWX.N^A01", "1994-01-01", "2026-01-01")
    assert ld.calls == ["TWX.N^A01"]
    assert not out.empty
    assert set(out["ric"]) == {"TWX.N^A01"}
