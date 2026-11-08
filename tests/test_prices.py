"""Synthetic checks for the price fetch/build chain (no API calls)."""

import pandas as pd

from factor_weaver.data import store
from factor_weaver.data.build.prices import _dividend_adjust, build_extra_prices, build_prices
from factor_weaver.data.fetch.lseg import _attempt, _covers, _try_lseg

_FIELDS = {
    "OPEN_PRC": [1.0],
    "HIGH_1": [1.5],
    "LOW_1": [0.5],
    "TRDPRC_1": [1.2],
    "ACVOL_UNS": [100],
}
_PRICE_COLS = ["date", "ric", "open", "high", "low", "close", "volume", "ret"]


class _FakeLD:
    def __init__(self, frames):
        self.frames = frames

    def get_history(self, universe, **kwargs):
        if universe not in self.frames:
            raise RuntimeError(f"{universe}: no data")
        return self.frames[universe]

    def get_data(self, universe, **kwargs):
        return pd.DataFrame()  # no TR.TotalReturn / dividend records


def _one_day_frame(close: float = 1.0):
    idx = pd.DatetimeIndex(pd.to_datetime(["2020-01-02"], utc=True), name="Date")
    return pd.DataFrame({k: [close if k == "TRDPRC_1" else 1.0] for k in _FIELDS}, index=idx)


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


_DAY = pd.Timestamp("2020-01-02")


def _lseg(frames, ric, query, first=_DAY):
    df, divs, err = _try_lseg(_FakeLD(frames), ric, query, "2020-01-01", "2020-02-01", first, _DAY)
    assert err is not None or divs.empty  # fake source has no dividend records
    return df, err


def test_try_lseg_relabels_query_ric_and_reports_errors():
    df, err = _lseg({"NEW.K": _one_day_frame()}, "OLD.N", "NEW.K")
    assert err is None and set(df["ric"]) == {"OLD.N"}  # rename → resolved RIC

    df, err = _lseg({"OLD.N": _one_day_frame()}, "OLD.N", "BOND=ARCA")
    assert err is None and set(df["ric"]) == {"OLD.N"}  # bad resolution → universe RIC

    df, err = _lseg({}, "OLD.N", "NEW.K")
    assert df.empty and err is not None and "NEW.K" in err and "OLD.N" in err

    frames = {"BRKb.N": _one_day_frame(1.0), "BRKa": _one_day_frame(9.0)}
    df, err = _lseg(frames, "BRKb.N", "BRKa")
    assert err is None and df["close"].tolist() == [1.0]  # other share class loses

    df, err = _lseg({"KO.N": _one_day_frame(1.0), "KO": _one_day_frame(9.0)}, "KO.N", "KO")
    assert err is None and df["close"].tolist() == [9.0]  # same line → consolidated RIC

    df, err = _lseg(
        {"KO.N": _one_day_frame(), "KO": _one_day_frame()},
        "KO.N",
        "KO",
        first=pd.Timestamp("2019-12-31"),
    )
    assert df.empty and err is not None and "no rows covering" in err


def test_covers_membership_window():
    df = pd.DataFrame({"date": pd.to_datetime(["2020-01-02", "2020-01-10"])})
    assert _covers(df, pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-10"))
    assert _covers(df, pd.Timestamp("2020-01-05"), pd.Timestamp("2020-01-07"))
    assert _covers(df, pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-12"))  # bar pre-weekend
    assert _covers(df, pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-17"))  # 7-day tolerance
    assert not _covers(df, pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-18"))
    assert not _covers(df, pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-10"))
    assert not _covers(df, pd.Timestamp("2020-01-02"), pd.Timestamp("2020-06-30"))
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
            "close_unadj": 1.0,
            "total_return": 0.0,
        }
    )


def _price_cfg(tmp_path, calendar: str = "2020-01-02") -> dict:
    """build_prices cfg with a ^SP500TR trading calendar of weekdays from `calendar`."""
    days = pd.bdate_range(calendar, "2020-01-31")
    cal = pd.DataFrame({"date": days, "symbol": "^SP500TR", "close": 1.0})
    store.write_parquet(cal, tmp_path / "extra_prices.parquet")
    return {
        "universe": {"assets_out": tmp_path / "assets.parquet"},
        "lseg": {"prices_out": tmp_path / "lseg", "dividends_out": tmp_path / "divs"},
        "yahoo": {"extra_prices_out": tmp_path / "extra_prices.parquet"},
        "prices": {"out": tmp_path / "prices.parquet"},
    }


def test_build_prices_assembles_lseg_caches_and_skips_missing(tmp_path):
    assets = pd.DataFrame({"ric": ["A.N", "B.N"]})
    store.write_parquet(assets, tmp_path / "assets.parquet")
    store.write_parquet(_cache_frame("A.N", ["2020-01-02"]), tmp_path / "lseg" / "A.N.parquet")
    cfg = _price_cfg(tmp_path)
    build_prices(cfg)
    prices = pd.read_parquet(tmp_path / "prices.parquet")
    assert list(prices.columns) == _PRICE_COLS
    assert set(prices["ric"]) == {"A.N"}  # no LSEG cache → missing, no other source


def test_build_prices_without_caches_raises(tmp_path):
    store.write_parquet(pd.DataFrame({"ric": ["B.N"]}), tmp_path / "assets.parquet")
    cfg = _price_cfg(tmp_path)
    try:
        build_prices(cfg)
    except RuntimeError as e:
        assert "no price data" in str(e)
    else:
        raise AssertionError("an empty LSEG cache dir must not produce a prices file")


def test_build_extra_prices_filters_and_writes(tmp_path):
    for symbol in ["^VIX", "AAPL"]:  # AAPL: a stray cache, not a configured extra
        frame = _cache_frame(symbol, ["2020-01-02"]).rename(columns={"ric": "symbol"})
        store.write_parquet(frame, tmp_path / "yahoo" / f"{symbol}.parquet")
    cfg = {
        "yahoo": {
            "prices_out": tmp_path / "yahoo",
            "extra_prices_out": tmp_path / "extra_prices.parquet",
            "extra_symbols": ["^VIX"],
        }
    }
    build_extra_prices(cfg)
    out = pd.read_parquet(tmp_path / "extra_prices.parquet")
    assert set(out["symbol"]) == {"^VIX"}


def _ex_day_frame(close: list[float], close_unadj: list[float]) -> pd.DataFrame:
    # 0.50 dividend goes ex on day 2 (2020-01-03)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
            "ric": "X.N",
            "open": [10.0, 9.5, 9.5],
            "high": [10.0, 9.5, 9.7],
            "low": [10.0, 9.5, 9.5],
            "close": close,
            "volume": [1, 2, 3],
            "close_unadj": close_unadj,
        }
    )


def _divs(div_type="Interim", payment_type="Cash Dividend") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ex_date": pd.to_datetime(["2020-01-03"]),
            "gross": [0.5],
            "div_type": [div_type],
            "payment_type": [payment_type],
        }
    )


def test_dividend_adjust_back_adjusts_before_ex_date_only():
    out, n = _dividend_adjust(_ex_day_frame([10.0, 9.5, 9.6], [10.0, 9.5, 9.6]), _divs())
    assert n == 1
    assert out["close"].round(6).tolist() == [9.5, 9.5, 9.6]  # day 1 × 9.5 / (9.5 + 0.5)
    assert out["open"].round(6).tolist() == [9.5, 9.5, 9.5]
    assert out["volume"].tolist() == [1, 2, 3]


def test_dividend_adjust_skips_dividends_rts_already_removed():
    # RTS already scaled day 1 by 0.95 (special removed); a second factor would double count
    out, n = _dividend_adjust(_ex_day_frame([9.5, 9.5, 9.6], [10.0, 9.5, 9.6]), _divs())
    assert n == 0
    assert out["close"].tolist() == [9.5, 9.5, 9.6]


def test_dividend_adjust_ignores_non_cash_and_rescinded_records():
    frame = _ex_day_frame([10.0, 9.5, 9.6], [10.0, 9.5, 9.6])
    for divs in [_divs(payment_type="Stock Dividend"), _divs(div_type="Rescinded payment")]:
        out, n = _dividend_adjust(frame.copy(), divs)
        assert n == 0 and out["close"].tolist() == [10.0, 9.5, 9.6]


def test_build_prices_applies_cached_dividends(tmp_path):
    store.write_parquet(pd.DataFrame({"ric": ["X.N"]}), tmp_path / "assets.parquet")
    frame = _ex_day_frame([10.0, 9.5, 9.6], [10.0, 9.5, 9.6]).assign(total_return=0.0)
    store.write_parquet(frame, tmp_path / "lseg" / "X.N.parquet")
    store.write_parquet(_divs(), tmp_path / "divs" / "X.N.parquet")
    cfg = _price_cfg(tmp_path)
    build_prices(cfg)
    prices = pd.read_parquet(tmp_path / "prices.parquet")
    assert list(prices.columns) == _PRICE_COLS
    assert prices["close"].round(6).tolist() == [9.5, 9.5, 9.6]


def test_build_prices_drops_off_calendar_rows_before_returns(tmp_path):
    store.write_parquet(pd.DataFrame({"ric": ["A.N"]}), tmp_path / "assets.parquet")
    dates = ["2020-01-02", "2020-01-03", "2020-01-04", "2020-01-06"]  # 01-04 is a Saturday
    frame = _cache_frame("A.N", dates).assign(close=[1.0, 2.0, 9.0, 3.0])
    store.write_parquet(frame.assign(close_unadj=frame["close"]), tmp_path / "lseg" / "A.N.parquet")
    build_prices(_price_cfg(tmp_path))
    prices = pd.read_parquet(tmp_path / "prices.parquet")
    assert prices["date"].dt.dayofweek.max() < 5
    assert prices["ret"].tolist()[1:] == [1.0, 0.5]  # Monday's return spans Friday
    assert pd.isna(prices["ret"].iloc[0])


def test_build_prices_rejects_a_calendar_shorter_than_prices(tmp_path):
    store.write_parquet(pd.DataFrame({"ric": ["A.N"]}), tmp_path / "assets.parquet")
    store.write_parquet(_cache_frame("A.N", ["2020-01-02"]), tmp_path / "lseg" / "A.N.parquet")
    try:
        build_prices(_price_cfg(tmp_path, calendar="2020-01-03"))
    except RuntimeError as e:
        assert "yahoo-prices --refresh" in str(e)
    else:
        raise AssertionError("prices before the calendar start must not be dropped silently")
