"""Synthetic checks for the fundamental feature build (no network)."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from factor_weaver.data.build.fundamental import (
    FUNDAMENTAL_FEATURES,
    asof_by_ric,
    build_fundamental,
    latest_rows,
    quarterly_panel,
)

_PERIODS = pd.date_range("2019-12-31", periods=13, freq="QE")
_LATEST_DATE = pd.Timestamp("2023-02-04")


def _rows(
    *, latest_equity: float = 500.0, include_cogs: bool = True, late_revenue: bool = False
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for i, period_end in enumerate(_PERIODS):
        source = period_end + pd.Timedelta(40, unit="D")
        announced = period_end + pd.Timedelta(41, unit="D")
        values = {
            "TR.F.TotRevenue": 100.0,
            "TR.F.COGSTot": 40.0,
            "TR.F.SGATot": 10.0,
            "TR.F.IntrExpn": 5.0,
            "TR.F.ShHoldEqCom": latest_equity if i == len(_PERIODS) - 1 else 500.0,
            "TR.F.TotAssets": 1000.0 + 100.0 * i,
            "TR.F.ComShrOutsTot": 110.0 if i == len(_PERIODS) - 1 else 100.0,
        }
        if late_revenue and i == 9:  # q-3 from the latest period
            source = pd.Timestamp("2023-03-01")
        if i == len(_PERIODS) - 1:
            source = pd.Timestamp("2023-02-01")
            announced = pd.NaT
        for field, value in values.items():
            if field == "TR.F.COGSTot" and not include_cogs:
                continue
            row = {
                "ric": "AAPL.OQ",
                "field": field,
                "value": value,
                "period_end": period_end,
                "fiscal_period": "Q",
                "source_date": source,
                "fund_upd_type": "Original",
                "original_announcement_date": announced,
            }
            if i == len(_PERIODS) - 1 and field == "TR.F.ShHoldEqCom":
                row["source_date"] = pd.NaT
                row["original_announcement_date"] = _LATEST_DATE
            rows.append(row)
    return pd.DataFrame(rows)


def _cfg(tmp_path: Path) -> dict[str, Any]:
    fund_dir = tmp_path / "fund"
    fund_dir.mkdir()
    assets = pd.DataFrame({"ric": ["AAPL.OQ"], "permid": ["123"]})
    assets.to_parquet(tmp_path / "assets.parquet")
    return {
        "universe": {
            "assets_out": str(tmp_path / "assets.parquet"),
            "start": "2020-01-01",
            "end": "2024-01-01",
        },
        "lseg": {
            "fundamentals_out": str(fund_dir),
            "market_cap_out": str(tmp_path / "caps.parquet"),
        },
        "prices": {"out": str(tmp_path / "prices.parquet")},
        "fundamental": {"out": str(tmp_path / "fundamental.parquet")},
    }


def _write_market_inputs(cfg: dict[str, Any]) -> None:
    feature_dates = [period + pd.Timedelta(41, unit="D") for period in _PERIODS]
    feature_dates[-1] = _LATEST_DATE
    prices = pd.DataFrame(
        {
            "date": list(_PERIODS) + feature_dates,
            "close": [10.0] * len(_PERIODS) + [12.0] * len(feature_dates),
            "ric": "AAPL.OQ",
        }
    )
    prices = prices.drop_duplicates(["date", "ric"]).sort_values(["date", "ric"])
    prices.to_parquet(Path(cfg["prices"]["out"]))
    caps = pd.DataFrame({"date": _PERIODS, "ric": "AAPL.OQ", "market_cap": 1000.0})
    caps.to_parquet(Path(cfg["lseg"]["market_cap_out"]))


def _write_fixture(
    tmp_path: Path,
    *,
    latest_equity: float = 500.0,
    include_cogs: bool = True,
    late_revenue: bool = False,
) -> dict[str, Any]:
    cfg = _cfg(tmp_path)
    _rows(
        latest_equity=latest_equity,
        include_cogs=include_cogs,
        late_revenue=late_revenue,
    ).to_parquet(Path(cfg["lseg"]["fundamentals_out"]) / "AAPL.OQ.parquet")
    _write_market_inputs(cfg)
    return cfg


def test_build_fundamental_values_and_date(tmp_path: Path) -> None:
    cfg = _write_fixture(tmp_path)
    build_fundamental(cfg)
    out = pd.read_parquet(Path(cfg["fundamental"]["out"]))

    assert list(out.columns) == ["date", "ric", "permid", *FUNDAMENTAL_FEATURES]
    assert not out.duplicated(["date", "ric"]).any()
    assert out.equals(out.sort_values(["date", "ric"]).reset_index(drop=True))

    latest = out.loc[out["date"] == _LATEST_DATE].iloc[0]
    assert latest["ric"] == "AAPL.OQ"
    assert latest["net_share_issuance"] == pytest.approx(np.log(1.1))
    assert latest["book_to_market"] == pytest.approx(500 / 1200)
    assert latest["operating_profitability"] == pytest.approx(180 / 500)
    assert latest["asset_growth"] == pytest.approx(2200 / 1800 - 1)
    assert latest["sales_to_price"] == pytest.approx(400 / 1200)


def test_missing_dates_use_60_day_fallback(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    rows = pd.DataFrame(
        {
            "ric": ["AAPL.OQ", "AAPL.OQ"],
            "field": ["TR.F.TotRevenue", "TR.F.TotRevenue"],
            "value": [100.0, 100.0],
            "period_end": [pd.Timestamp("2020-03-31"), pd.Timestamp("2020-06-30")],
            "fiscal_period": ["Q", "Q"],
            "source_date": [pd.NaT, pd.NaT],
            "fund_upd_type": ["Original", "Original"],
            "original_announcement_date": [pd.NaT, pd.NaT],
        }
    )
    rows.to_parquet(Path(cfg["lseg"]["fundamentals_out"]) / "AAPL.OQ.parquet")
    panel = quarterly_panel(cfg).set_index("period_end")

    assert panel.loc[pd.Timestamp("2020-03-31"), "date"] == pd.Timestamp("2020-05-30")
    assert panel.loc[pd.Timestamp("2020-06-30"), "date"] == pd.Timestamp("2020-08-29")


def test_latest_rows_drops_stale_and_duplicate_dates() -> None:
    rows = pd.DataFrame(
        {
            "ric": ["A", "A", "A", "B"],
            "date": pd.to_datetime(
                ["2020-04-01", "2020-04-01", "2020-05-01", "2020-04-01"]
            ),
            "period_end": pd.to_datetime(
                ["2019-12-31", "2020-03-31", "2019-09-30", "2019-12-31"]
            ),
        }
    )
    out = latest_rows(rows)
    assert list(out.loc[out["ric"] == "A", "period_end"]) == [pd.Timestamp("2020-03-31")]
    assert list(out.loc[out["ric"] == "B", "period_end"]) == [pd.Timestamp("2019-12-31")]


def test_asof_missing_right_keeps_left_key() -> None:
    left = pd.DataFrame({"ric": ["A"], "date": [pd.Timestamp("2020-01-02")]})
    right = pd.DataFrame(
        {"ric": ["B"], "date": [pd.Timestamp("2020-01-01")], "close": [10.0]}
    )
    out = asof_by_ric(left, right, "date", "date")
    assert out.loc[0, "date"] == pd.Timestamp("2020-01-02")
    assert pd.isna(out.loc[0, "close"])


def test_late_lagged_input_is_not_used(tmp_path: Path) -> None:
    cfg = _write_fixture(tmp_path, late_revenue=True)
    build_fundamental(cfg)
    out = pd.read_parquet(Path(cfg["fundamental"]["out"]))
    latest = out.loc[out["date"] == _LATEST_DATE].iloc[0]

    assert pd.isna(latest["operating_profitability"])
    assert pd.isna(latest["sales_to_price"])
    assert latest["book_to_market"] == pytest.approx(500 / 1200)


def test_nonpositive_equity_disables_book_and_profitability(tmp_path: Path) -> None:
    cfg = _write_fixture(tmp_path, latest_equity=0.0)
    build_fundamental(cfg)
    out = pd.read_parquet(Path(cfg["fundamental"]["out"]))
    latest = out.loc[out["date"] == _LATEST_DATE].iloc[0]

    assert pd.isna(latest["book_to_market"])
    assert pd.isna(latest["operating_profitability"])
    assert latest["sales_to_price"] == pytest.approx(400 / 1200)


def test_missing_cogs_is_zero(tmp_path: Path) -> None:
    cfg = _write_fixture(tmp_path, include_cogs=False)
    build_fundamental(cfg)
    out = pd.read_parquet(Path(cfg["fundamental"]["out"]))
    latest = out.loc[out["date"] == _LATEST_DATE].iloc[0]

    assert latest["operating_profitability"] == pytest.approx(340 / 500)
