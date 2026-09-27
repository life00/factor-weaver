"""Synthetic checks for the price source chain and cache paths (no API calls)."""

import pandas as pd

from factor_weaver.data.prices import _attempt, _cache_path, _covers, _try_lseg

_FIELDS = {
    "OPEN_PRC": [1.0],
    "HIGH_1": [1.5],
    "LOW_1": [0.5],
    "TRDPRC_1": [1.2],
    "ACVOL_UNS": [100],
}


class _FakeLD:
    def __init__(self, frames):
        self.frames = frames

    def get_history(self, universe, **kwargs):
        if universe not in self.frames:
            raise RuntimeError(f"{universe}: no data")
        return self.frames[universe]


def _one_day_frame():
    idx = pd.DatetimeIndex(pd.to_datetime(["2020-01-02"], utc=True), name="Date")
    return pd.DataFrame({k: [1.0] for k in _FIELDS}, index=idx)


def _raise():
    raise RuntimeError("boom\nsecond line")


def test_cache_path_flat_and_collision_free(tmp_path):
    assert _cache_path(tmp_path, ".SPX").name == ".SPX.parquet"
    assert _cache_path(tmp_path, "TWX.N^A01") != _cache_path(tmp_path, "TWX.N_A01")


def test_attempt_reports_errors_and_empty():
    df, err = _attempt(lambda: pd.DataFrame())
    assert df.empty and err == "no usable rows"
    df, err = _attempt(_raise)
    assert df.empty and err == "boom"
    df, err = _attempt(_one_day_frame)
    assert err is None and len(df) == 1


def test_try_lseg_relabels_fallback_and_reports_errors():
    df, err = _try_lseg(
        _FakeLD({"ALT.N": _one_day_frame()}), "OLD.N", "ALT.N", "2020-01-01", "2020-02-01"
    )
    assert err is None and set(df["ric"]) == {"OLD.N"}

    df, err = _try_lseg(_FakeLD({}), "OLD.N", None, "2020-01-01", "2020-02-01")
    assert df.empty and err is not None

    df, err = _try_lseg(_FakeLD({}), "OLD.N", "ALT.N", "2020-01-01", "2020-02-01")
    assert df.empty and err is not None and "fallback ALT.N" in err


def test_covers_membership_window():
    df = pd.DataFrame({"date": pd.to_datetime(["2020-01-02", "2020-01-10"])})
    assert _covers(df, pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-10"))
    assert _covers(df, pd.Timestamp("2020-01-05"), pd.Timestamp("2020-01-07"))
    assert not _covers(df, pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-10"))  # starts late
    assert not _covers(df, pd.Timestamp("2020-01-02"), pd.Timestamp("2020-06-30"))  # ends early
    assert not _covers(
        pd.DataFrame(columns=["date"]), pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-02")
    )
