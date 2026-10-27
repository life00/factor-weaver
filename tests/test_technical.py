"""Synthetic checks for the technical feature build (no network)."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from factor_weaver.data.build.technical import TECHNICAL_FEATURES, build_technical

_START = pd.Timestamp("2020-01-01")


def _cfg(tmp_path: Path) -> dict[str, Any]:
    fund_dir = tmp_path / "fund"
    fund_dir.mkdir()
    return {
        "universe": {
            "assets_out": str(tmp_path / "assets.parquet"),
            "start": "2020-01-01",
            "end": "2021-12-31",
        },
        "lseg": {
            "fundamentals_out": str(fund_dir),
            "market_cap_out": str(tmp_path / "caps.parquet"),
        },
        "prices": {"out": str(tmp_path / "prices.parquet")},
        "technical": {"out": str(tmp_path / "technical.parquet")},
    }


def _write_fixture(tmp_path: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    cfg = _cfg(tmp_path)
    prices = pd.DataFrame(
        {
            "date": pd.bdate_range(_START, periods=300),
            "ric": "AAPL.OQ",
            "close": 100.0 * 1.01 ** np.arange(300),
            "volume": 1000.0,
        }
    )
    prices.to_parquet(Path(cfg["prices"]["out"]))
    assets = pd.DataFrame({"ric": ["AAPL.OQ"], "permid": ["123"]})
    assets.to_parquet(Path(cfg["universe"]["assets_out"]))
    caps = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-03-31", "2020-06-30"]),
            "ric": "AAPL.OQ",
            "market_cap": [100_000.0, 200_000.0],
        }
    )
    caps.to_parquet(Path(cfg["lseg"]["market_cap_out"]))

    shares = pd.DataFrame(
        {
            "ric": ["AAPL.OQ", "AAPL.OQ"],
            "field": ["TR.F.ComShrOutsTot", "TR.F.ComShrOutsTot"],
            "value": [100.0, 200.0],
            "period_end": pd.to_datetime(["2019-12-31", "2020-03-31"]),
            "fiscal_period": ["Q", "Q"],
            "source_date": pd.to_datetime(["2020-04-15", "2020-06-01"]),
            "fund_upd_type": ["Original", "Original"],
            "original_announcement_date": [pd.NaT, pd.NaT],
        }
    )
    shares.to_parquet(Path(cfg["lseg"]["fundamentals_out"]) / "AAPL.OQ.parquet")
    return cfg, prices


def test_build_technical_values(tmp_path: Path) -> None:
    cfg, prices = _write_fixture(tmp_path)
    build_technical(cfg)
    out = pd.read_parquet(Path(cfg["technical"]["out"]))
    prices = prices.set_index("date")

    assert list(out.columns) == ["date", "ric", "permid", *TECHNICAL_FEATURES]
    assert not out.duplicated(["date", "ric"]).any()
    assert out.equals(out.sort_values(["date", "ric"]).reset_index(drop=True))
    assert out["date"].min() >= pd.Timestamp("2020-01-01")
    assert out["date"].max() < pd.Timestamp("2021-12-31")
    assert pd.Timestamp("2020-01-01") not in set(out["date"])

    last = out.iloc[-1]
    assert last["date"] == prices.index[-1]
    assert last["momentum"] == pytest.approx(1.01**231 - 1)
    assert last["short_term_reversal"] == pytest.approx(1.01**21 - 1)
    assert last["volatility"] == pytest.approx(0.0, abs=1e-12)
    assert last["share_turnover"] == pytest.approx(21 * 1000 / 200)

    size_apr = out.loc[out["date"] == pd.Timestamp("2020-04-15"), "size"].iloc[0]
    expected_apr = np.log(
        100_000 * prices.loc[pd.Timestamp("2020-04-15"), "close"]
        / prices.loc[pd.Timestamp("2020-03-31"), "close"]
    )
    assert size_apr == pytest.approx(expected_apr)

    size_jul = out.loc[out["date"] == pd.Timestamp("2020-07-15"), "size"].iloc[0]
    expected_jul = np.log(
        200_000 * prices.loc[pd.Timestamp("2020-07-15"), "close"]
        / prices.loc[pd.Timestamp("2020-06-30"), "close"]
    )
    assert size_jul == pytest.approx(expected_jul)

    may = out.loc[out["date"] == pd.Timestamp("2020-05-29"), "share_turnover"].iloc[0]
    june = out.loc[out["date"] == pd.Timestamp("2020-06-01"), "share_turnover"].iloc[0]
    assert may == pytest.approx(21 * 1000 / 100)
    assert june == pytest.approx(21 * 1000 / 200)

    stale = out.loc[out["date"] == pd.Timestamp("2020-12-31")].iloc[0]
    assert pd.isna(stale["size"])
    assert not pd.isna(stale["momentum"])
    assert not pd.isna(stale["short_term_reversal"])
    assert not pd.isna(stale["share_turnover"])
