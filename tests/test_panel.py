"""Synthetic checks for the align and clean panel steps (no network)."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from factor_weaver.data.build.behavioral import FEATURES as BEHAVIORAL_FEATURES
from factor_weaver.data.build.fundamental import FUNDAMENTAL_FEATURES
from factor_weaver.data.build.panel import FEATURES, align_panel, clean_panel
from factor_weaver.data.build.technical import TECHNICAL_FEATURES

CAL = pd.bdate_range("2020-03-31", "2020-09-30")  # stand-in exchange calendar
Q2, Q3 = CAL[(CAL > "2020-03-31") & (CAL <= "2020-06-30")], CAL[CAL > "2020-06-30"]
NO_IRX = pd.Timestamp("2020-05-25")  # a stock trading day without a T-bill quote
SP = pd.Series(1000.0 * 1.002 ** np.arange(len(CAL)), index=CAL)
IRX = pd.Series(1.0 + 0.01 * np.arange(len(CAL)), index=CAL).drop(NO_IRX)
VIX = pd.Series(20.0 + 0.1 * np.arange(len(CAL)), index=CAL)


def _cfg(tmp_path: Path) -> dict[str, Any]:
    p = {k: str(tmp_path / f"{k}.parquet") for k in ("u", "px", "x", "t", "f", "b", "a", "c")}
    return {
        "universe": {"universe_out": p["u"], "start": "2020-03-31", "end": "2020-10-01"},
        "prices": {"out": p["px"]},
        "yahoo": {"extra_prices_out": p["x"]},
        "technical": {"out": p["t"]},
        "fundamental": {"out": p["f"]},
        "marketpsych": {"out": p["b"]},
        "align": {"out": p["a"], "fundamental_max_age_days": 365},
        "clean": {"out": p["c"]},
    }


def _rows(dates: Any, ric: str, cols: list[str], **values: Any) -> pd.DataFrame:
    df = pd.DataFrame({"date": pd.DatetimeIndex(dates), "ric": ric, "permid": ric.lower()})
    for col in cols:
        df[col] = values.get(col, np.nan)
    return df


@pytest.fixture
def aligned(tmp_path: Path) -> pd.DataFrame:
    cfg = _cfg(tmp_path)
    # A member throughout; B leaves after Q2; C enters in Q3
    pd.DataFrame(
        {
            "quarter_end": pd.to_datetime(["2020-03-31"] * 2 + ["2020-06-30"] * 2),
            "ric": ["A", "B", "A", "C"],
            "permid": ["a", "b", "a", "c"],
        }
    ).to_parquet(cfg["universe"]["universe_out"])
    pd.concat(
        [
            pd.DataFrame({"date": s.index, "symbol": sym, "close": s.to_numpy()})
            for sym, s in (("^SP500TR", SP), ("^IRX", IRX), ("^VIX", VIX))
        ]
    ).to_parquet(cfg["yahoo"]["extra_prices_out"])

    b_days = CAL[CAL <= "2020-05-29"]  # delisted: no prices in June
    prices = pd.concat(  # as build_prices writes them: calendar-aligned, with ret
        [
            pd.DataFrame({"date": CAL, "ric": "A", "close": 100.0 * 1.01 ** np.arange(len(CAL))}),
            pd.DataFrame({"date": b_days, "ric": "B", "close": 50.0}),
            pd.DataFrame({"date": CAL, "ric": "C", "close": 10.0}),
        ]
    )
    prices["ret"] = prices.groupby("ric")["close"].pct_change()
    prices.to_parquet(cfg["prices"]["out"])
    pd.concat(
        [_rows(d, r, TECHNICAL_FEATURES, momentum=1.0) for r, d in zip("ABC", (CAL, b_days, CAL))]
    ).to_parquet(cfg["technical"]["out"])
    _rows(CAL, "A", BEHAVIORAL_FEATURES, sentiment=0.5).to_parquet(cfg["marketpsych"]["out"])
    pd.concat(
        [
            _rows(["2020-04-03"], "A", FUNDAMENTAL_FEATURES, net_share_issuance=1.0),  # Friday
            _rows(["2019-04-15"], "B", FUNDAMENTAL_FEATURES, book_to_market=3.0),  # ages out
            _rows(["2019-01-02"], "C", FUNDAMENTAL_FEATURES, asset_growth=2.0),  # too old
        ]
    ).to_parquet(cfg["fundamental"]["out"])

    align_panel(cfg)
    return pd.read_parquet(cfg["align"]["out"]).set_index(["ric", "date"])


def test_member_grid_covers_every_trading_day_of_the_quarter(aligned: pd.DataFrame) -> None:
    days = {r: aligned.xs(r).index for r in "ABC"}
    assert days["A"].equals(Q2.union(Q3))
    assert days["B"].equals(Q2)  # kept through the delisting tail
    assert days["C"].equals(Q3)
    assert (aligned.index.get_level_values("date").dayofweek < 5).all()


def test_close_and_return_from_prices(aligned: pd.DataFrame) -> None:
    a = aligned.xs("A")
    assert a.loc[CAL[1], "ret"] == pytest.approx(0.01)  # first member day, prior close 03-31
    assert a.loc[CAL[1], "close"] == pytest.approx(101.0)
    tail = aligned.xs("B").loc["2020-06-01":]
    assert len(tail) > 0 and tail[["close", "ret", "momentum"]].isna().all().all()


def test_market_columns(aligned: pd.DataFrame) -> None:
    a = aligned.xs("A")
    t = Q2[10]
    prev = CAL[CAL.get_loc(t) - 1]
    assert a.loc[t, "rf"] == pytest.approx(IRX[prev] / 100 / 252)  # yield of t-1
    after = CAL[CAL.get_loc(NO_IRX) + 1]  # its t-1 has no quote: carry the day before
    assert a.loc[after, "rf"] == pytest.approx(IRX[CAL[CAL.get_loc(NO_IRX) - 1]] / 100 / 252)
    assert a.loc[t, "mkt_ret"] == pytest.approx(SP[t] / SP[prev] - 1)
    assert a.loc[t, "vix"] == VIX[t]  # same-day close, not lagged
    market = aligned[["rf", "mkt_ret", "vix"]]
    assert market.notna().all().all()
    assert (market.groupby(level="date").nunique() == 1).all().all()  # same for every member


def test_fundamentals_enter_next_trading_day_and_expire(aligned: pd.DataFrame) -> None:
    a, b = aligned.xs("A"), aligned.xs("B")
    assert np.isnan(a.loc["2020-04-03", "net_share_issuance"])
    assert a.loc["2020-04-06", "net_share_issuance"] == 1.0
    assert b.loc["2020-04-14", "book_to_market"] == 3.0  # 365 days old
    assert np.isnan(b.loc["2020-04-15", "book_to_market"])  # 366 days old
    assert aligned.xs("C")["asset_growth"].isna().all()


def test_clean_ranks_features_and_leaves_prices(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-02"] * 4 + ["2020-01-03"] * 2),
            "ric": ["A", "B", "C", "D", "A", "B"],
            "permid": ["a", "b", "c", "d", "a", "b"],
            "close": [1.0, np.nan, 3.0, 4.0, 5.0, 6.0],
            "ret": [np.nan, 0.1, -0.2, 0.3, 0.4, np.nan],
            "rf": [1e-4] * 4 + [2e-4] * 2,
            "mkt_ret": [0.01] * 4 + [np.nan] * 2,
            "vix": [20.0] * 4 + [21.0] * 2,
        }
    )
    for f in FEATURES:
        df[f] = np.nan
    df["momentum"] = [1.0, 2.0, 2.0, np.nan, 7.0, np.nan]
    df["size"] = [5.0, 9.0, 1.0, 3.0, 0.0, 0.0]
    df.to_parquet(cfg["align"]["out"])

    clean_panel(cfg)
    out = pd.read_parquet(cfg["clean"]["out"])
    assert out["momentum"].tolist() == [-1.0, 0.5, 0.5, 0.0, 0.0, 0.0]  # ties, NaN, n == 1
    assert out["size"].tolist() == pytest.approx([1 / 3, 1.0, -1.0, -1 / 3, 0.0, 0.0])
    assert not out[FEATURES].isna().any().any()
    keep = ["date", "ric", "close", "ret", "rf", "mkt_ret", "vix"]
    pd.testing.assert_frame_equal(out[keep], df[keep])
