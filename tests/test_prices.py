"""Synthetic checks for the price fetch/build chain (no API calls)."""

import pandas as pd

from factor_weaver.data import store
from factor_weaver.data.build.prices import _covers, _write_extra_prices, build_prices
from factor_weaver.data.fetch.prices import _attempt, _try_lseg

_FIELDS = {
    "OPEN_PRC": [1.0],
    "HIGH_1": [1.5],
    "LOW_1": [0.5],
    "TRDPRC_1": [1.2],
    "ACVOL_UNS": [100],
}
_PRICE_COLS = ["date", "ric", "open", "high", "low", "close", "volume"]


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
    assert store.cache_path(tmp_path, ".SPX", url_quote=True).name == ".SPX.parquet"
    assert store.cache_path(tmp_path, "TWX.N^A01", url_quote=True) != store.cache_path(
        tmp_path, "TWX.N_A01", url_quote=True
    )
    assert store.cache_path(tmp_path, "^VIX").name == "^VIX.parquet"


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


def _cache_frame(ric: str, dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "ric": ric,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 0,
        }
    )


def test_build_prices_prefers_lseg_then_validated_fallback(tmp_path):
    assets = pd.DataFrame(
        {
            "ric": ["A.N", "B.N"],
            "ticker": ["A", "B"],
            "first_quarter_end": pd.to_datetime(["2020-01-02", "2020-01-02"]),
            "last_quarter_end": pd.to_datetime(["2020-01-10", "2020-01-10"]),
        }
    )
    store.write_parquet(assets, tmp_path / "assets.parquet")
    store.write_parquet(_cache_frame("A.N", ["2020-01-02"]), tmp_path / "lseg" / "A.N.parquet")
    store.write_parquet(
        _cache_frame("B", ["2020-01-02", "2020-01-10"]), tmp_path / "yahoo" / "B.parquet"
    )
    cfg = {
        "universe": {"assets_out": tmp_path / "assets.parquet"},
        "lseg": {"prices_out": tmp_path / "lseg"},
        "yahoo": {
            "prices_out": tmp_path / "yahoo",
            "extra_prices_out": tmp_path / "extra.parquet",
            "extra_symbols": ["^GSPC"],
            "symbol_overrides": {},
        },
        "prices": {"out": tmp_path / "prices.parquet"},
    }
    build_prices(cfg)
    prices = pd.read_parquet(tmp_path / "prices.parquet")
    assert list(prices.columns) == _PRICE_COLS
    assert set(prices["ric"]) == {"A.N", "B.N"}
    assert (prices.loc[prices["ric"] == "B.N", "date"].min()) == pd.Timestamp("2020-01-02")


def test_build_prices_drops_fallback_without_coverage(tmp_path):
    assets = pd.DataFrame(
        {
            "ric": ["B.N"],
            "ticker": ["B"],
            "first_quarter_end": pd.to_datetime(["2020-01-02"]),
            "last_quarter_end": pd.to_datetime(["2020-06-30"]),
        }
    )
    store.write_parquet(assets, tmp_path / "assets.parquet")
    store.write_parquet(_cache_frame("B", ["2020-01-02"]), tmp_path / "yahoo" / "B.parquet")
    cfg = {
        "universe": {"assets_out": tmp_path / "assets.parquet"},
        "lseg": {"prices_out": tmp_path / "lseg"},
        "yahoo": {
            "prices_out": tmp_path / "yahoo",
            "extra_prices_out": tmp_path / "extra.parquet",
            "extra_symbols": [],
        },
    }
    try:
        build_prices(cfg)
    except RuntimeError as e:
        assert "no price data" in str(e)
    else:
        raise AssertionError("short Yahoo fallback must not be assembled")


def test_write_extra_prices_filters_and_writes(tmp_path):
    frame = _cache_frame("^VIX", ["2020-01-02"]).rename(columns={"ric": "symbol"})
    store.write_parquet(frame, tmp_path / "yahoo" / "^VIX.parquet")
    cfg = {
        "yahoo": {
            "extra_prices_out": tmp_path / "extra_prices.parquet",
            "extra_symbols": ["^VIX"],
        }
    }
    _write_extra_prices(cfg, tmp_path / "yahoo")
    out = pd.read_parquet(tmp_path / "extra_prices.parquet")
    assert set(out["symbol"]) == {"^VIX"}
