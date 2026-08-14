"""Synthetic end-to-end check of build_universe reconstruction + ranking.

Fixture mimics the real LSEG artifacts: Arrow string[python] dtypes (locks the
merge_asof dtype regression), a phantom full-constituents baseline dated before
the data window (locks the baseline skip), and a retired ^-suffixed RIC with no
LSEG ticker (locks delisted flag + generated ticker).
"""

import pandas as pd
import pytest

from factor_weaver.data.universe import build_universe

RIC = {"A": "A.N", "B": "B.N", "C": "C.N", "D": "D.N", "E": "E.N^X99"}


def _arrow(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype("string[python]")
    return df


def _write(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _arrow(df).to_parquet(path, index=False)


@pytest.fixture
def cfg(tmp_path):
    f = tmp_path / "f"
    g = tmp_path / "g"
    _write(
        pd.DataFrame({"ric": [RIC["A"], RIC["B"], RIC["D"], RIC["E"]]}), f / "constituents.parquet"
    )
    _write(
        pd.DataFrame(
            {
                "date": pd.to_datetime(["2019-12-30"] * 4 + ["2020-06-10", "2020-06-15"]),
                "ric": [RIC["A"], RIC["B"], RIC["D"], RIC["E"], RIC["C"], RIC["D"]],
                "change": ["Joiner"] * 4 + ["Leaver", "Joiner"],
            }
        ),
        f / "joiners_leavers.parquet",
    )
    _write(
        pd.DataFrame(
            {
                "ric": list(RIC.values()),
                "ticker": ["A", "B", "C", "D", None],
            }
        ),
        f / "mapping.parquet",
    )
    _write(
        pd.DataFrame(
            {
                "ric": [
                    RIC["A"],
                    RIC["A"],
                    RIC["A"],
                    RIC["B"],
                    RIC["B"],
                    RIC["B"],
                    RIC["C"],
                    RIC["D"],
                    RIC["D"],
                    RIC["E"],
                    RIC["E"],
                    RIC["E"],
                ],
                "date": pd.to_datetime(
                    ["2020-03-31", "2020-06-30", "2021-03-31"] * 3
                    + ["2020-03-31", "2020-06-30", "2021-03-31"]
                ),
                "market_cap": [100, 90, 120, 50, 50, 50, 30, 80, 70, 40, 40, 40],
            }
        ),
        f / "market_cap.parquet",
    )
    return {
        "lseg": {
            "start": "20200101",
            "constituents_out": f / "constituents.parquet",
            "joiners_leavers_out": f / "joiners_leavers.parquet",
            "mapping_out": f / "mapping.parquet",
            "market_cap_out": f / "market_cap.parquet",
        },
        "universe": {"top_n": 2, "out": g / "universe.parquet"},
    }


def test_membership_reconstruction(cfg):
    cfg["universe"]["top_n"] = 4
    build_universe(cfg)
    df = pd.read_parquet(cfg["universe"]["out"])
    by_q = df.groupby("quarter_end")["ric"].apply(set)
    assert by_q[pd.Timestamp("2020-03-31")] == {"A.N", "B.N", "C.N", "E.N^X99"}
    assert by_q[pd.Timestamp("2020-06-30")] == {"A.N", "B.N", "D.N", "E.N^X99"}
    assert by_q[pd.Timestamp("2021-03-31")] == {"A.N", "B.N", "D.N", "E.N^X99"}


def test_ranking(cfg):
    build_universe(cfg)
    df = pd.read_parquet(cfg["universe"]["out"])
    rows = df[df["quarter_end"] == pd.Timestamp("2020-06-30")]
    assert list(rows["rank"]) == [1, 2]
    assert list(rows["ric"]) == ["A.N", "D.N"]
    assert list(rows["ticker"]) == ["A", "D"]
    ranges = [sorted(set(g["rank"])) for _, g in df.groupby("quarter_end")]
    assert all(r == [1, 2] for r in ranges)


def test_delisted_flag(cfg):
    cfg["universe"]["top_n"] = 3
    build_universe(cfg)
    df = pd.read_parquet(cfg["universe"]["out"])
    e = df.loc[df["ric"] == RIC["E"], "delisted"]
    assert len(e) and bool(e.all())
    assert set(df.loc[df["ric"] == RIC["E"], "ticker"]) == {"E"}
    a = df.loc[df["ric"] == RIC["A"], "delisted"]
    assert len(a) and not bool(a.any())
