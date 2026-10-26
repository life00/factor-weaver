"""Synthetic checks for LSEG fundamentals normalization, caching and failures (no API)."""

from contextlib import nullcontext
from types import SimpleNamespace

import pandas as pd
import pytest

from factor_weaver.data import pipeline, store
from factor_weaver.data.fetch import lseg
from factor_weaver.data.fetch.lseg import (
    _FUND_OUT_COLS,
    _fund_columns,
    _normalize_fundamentals,
    fetch_fundamentals,
)

_IS_FIELDS = ["TR.F.TotRevenue", "TR.F.COGSTot", "TR.F.SGATot", "TR.F.IntrExpn"]
_BS_FIELDS = ["TR.F.ShHoldEqCom", "TR.F.TotAssets", "TR.F.ComShrOutsTot"]


def _frame(fields, values, announcement_col, announcement, period_end="2020-03-31"):
    row = {
        "Instrument": "AAPL.O",
        "TR.F.PeriodEndDate": period_end,
        "TR.F.SourceDate": "2020-04-20",
        "TR.F.SourceDate.FundUpdType": "Original",
        announcement_col: announcement,
    }
    for field, value in zip(fields, values):
        row[field] = value
        row[f"{field}.date"] = period_end
        row[f"{field}.calcdate"] = "2020-04-21"
        row[f"{field}.fperiod"] = "FQ1 2020"
    return pd.DataFrame([row])


def _is_frame():
    return _frame(
        _IS_FIELDS, [100.0, 40.0, 20.0, 5.0], "TR.ISOriginalAnnouncementDate", "2020-04-16"
    )


def _bs_frame():
    return _frame(
        _BS_FIELDS, [50.0, 300.0, 10.0], "TR.BSOriginalAnnouncementDate", "2020-04-17"
    )


class _FakeDefinition:
    def __init__(self, ld, fields):
        self.ld = ld
        self.fields = fields

    def get_data(self):
        self.ld.calls += 1
        if self.ld.fail_is and "TR.F.TotRevenue" in self.fields:
            raise RuntimeError("entitlement denied")
        df = _is_frame() if "TR.F.TotRevenue" in self.fields else _bs_frame()
        if self.ld.no_values:
            for field in _IS_FIELDS + _BS_FIELDS:
                if field in df.columns:
                    df[field] = pd.NA
        df.index = pd.DatetimeIndex(df["TR.F.PeriodEndDate"])
        return SimpleNamespace(is_success=True, data=SimpleNamespace(df=df))


class _FakeFundamentals:
    class RowHeaders:
        DATE = "date"

    def __init__(self, ld):
        self.ld = ld

    def Definition(self, universe, fields, parameters, row_headers, header_type):  # noqa: N802
        self.ld.row_headers.append(row_headers)
        return _FakeDefinition(self.ld, fields)


class _FakeLD:
    class HeaderType:
        NAME = "name"

    def __init__(self, fail_is=False, no_values=False):
        self.fail_is = fail_is
        self.no_values = no_values
        self.calls = 0
        self.row_headers = []
        self.content = SimpleNamespace(fundamental_and_reference=_FakeFundamentals(self))

    def get_config(self):
        return self

    def set_param(self, *args, **kwargs):
        pass


def _cfg(tmp_path):
    assets = tmp_path / "assets.parquet"
    pd.DataFrame({"ric": ["AAPL.O"], "permid": ["4295904307"]}).to_parquet(assets, index=False)
    return {
        "universe": {"assets_out": str(assets), "start": "2020-01-01", "end": "2020-12-31"},
        "lseg": {"fundamentals_out": str(tmp_path / "fund")},
    }


@pytest.fixture
def fake(monkeypatch):
    ld = _FakeLD()
    monkeypatch.setattr(lseg, "session", lambda: nullcontext(ld))
    monkeypatch.setattr(lseg, "resolve_permids", lambda ld, permids: {})
    return ld


def test_fund_columns_restores_repeated_suffix_headers():
    # Live NAME headers repeat the base field for value/date/calcdate/fperiod.
    fields = [
        "TR.F.TotRevenue",
        "TR.F.TotRevenue.date",
        "TR.F.SourceDate",
        "TR.F.SourceDate.FundUpdType",
    ]
    df = pd.DataFrame(
        [["AAPL.O", 1.0, "2020-03-31", "2020-04-20", "Original"]],
        columns=[
            "Instrument",
            "TR.F.TotRevenue",
            "TR.F.TotRevenue",
            "TR.F.SourceDate",
            "TR.F.SourceDate",
        ],
    )
    assert list(_fund_columns(df, fields).columns) == ["Instrument", *fields]


def test_normalize_fundamentals_schema_and_dates():
    out = pd.concat(
        [
            _normalize_fundamentals(
                _is_frame(), "AAPL.N", _IS_FIELDS, "TR.ISOriginalAnnouncementDate", "is"
            ),
            _normalize_fundamentals(
                _bs_frame(), "AAPL.N", _BS_FIELDS, "TR.BSOriginalAnnouncementDate", "bs"
            ),
        ]
    )
    assert list(out.columns) == _FUND_OUT_COLS
    assert len(out) == 7
    assert set(out["ric"]) == {"AAPL.N"}
    assert out["date"].eq(pd.Timestamp("2020-03-31")).all()
    assert out["period_end"].notna().all()
    assert out["source_date"].eq(pd.Timestamp("2020-04-20")).all()
    assert out["calc_date"].eq(pd.Timestamp("2020-04-21")).all()
    assert out["fund_upd_type"].eq("Original").all()
    revenue = out.set_index("field").loc["TR.F.TotRevenue"]
    total_assets = out.set_index("field").loc["TR.F.TotAssets"]
    assert revenue["original_announcement_date"] == pd.Timestamp("2020-04-16")
    assert total_assets["original_announcement_date"] == pd.Timestamp("2020-04-17")
    assert revenue["statement_type"] == "is"
    assert total_assets["statement_type"] == "bs"


def test_normalize_fundamentals_empty():
    out = _normalize_fundamentals(pd.DataFrame(), "AAPL.O", _IS_FIELDS, "x", "is")
    assert out.empty
    assert list(out.columns) == _FUND_OUT_COLS


def test_normalize_fundamentals_skips_missing_field():
    df = _is_frame().drop(columns=["TR.F.IntrExpn"])
    out = _normalize_fundamentals(df, "AAPL.O", _IS_FIELDS, "TR.ISOriginalAnnouncementDate", "is")
    assert len(out) == 3
    assert "TR.F.IntrExpn" not in set(out["field"])


def test_normalize_fundamentals_fills_nat_field_date():
    df = _is_frame()
    df["TR.F.TotRevenue.date"] = pd.NaT
    out = _normalize_fundamentals(df, "AAPL.O", _IS_FIELDS, "TR.ISOriginalAnnouncementDate", "is")
    revenue = out.set_index("field").loc["TR.F.TotRevenue"]
    assert revenue["date"] == revenue["period_end"] == pd.Timestamp("2020-03-31")


def test_normalize_fundamentals_fills_missing_period_end_from_index():
    df = _is_frame()
    df.index = pd.DatetimeIndex(df["TR.F.PeriodEndDate"])
    df["TR.F.PeriodEndDate"] = pd.NA
    out = _normalize_fundamentals(df, "AAPL.O", _IS_FIELDS, "TR.ISOriginalAnnouncementDate", "is")
    assert out["period_end"].eq(pd.Timestamp("2020-03-31")).all()


def test_fetch_fundamentals_writes_raw(tmp_path, fake):
    cfg = _cfg(tmp_path)
    fetch_fundamentals(cfg)
    path = store.cache_path(tmp_path / "fund", "AAPL.O", url_quote=True)
    out = pd.read_parquet(path)
    assert list(out.columns) == _FUND_OUT_COLS
    assert len(out) == 7
    assert set(out["ric"]) == {"AAPL.O"}
    assert fake.row_headers == [["date"], ["date"]]


def test_fetch_fundamentals_cache_skip_and_refresh(tmp_path, fake):
    cfg = _cfg(tmp_path)
    fetch_fundamentals(cfg)
    assert fake.calls == 2
    fetch_fundamentals(cfg)
    assert fake.calls == 2
    cfg["_refresh"] = True
    fetch_fundamentals(cfg)
    assert fake.calls == 4


def test_fetch_fundamentals_failure_raises(tmp_path, monkeypatch):
    ld = _FakeLD(fail_is=True)
    monkeypatch.setattr(lseg, "session", lambda: nullcontext(ld))
    monkeypatch.setattr(lseg, "resolve_permids", lambda ld, permids: {})
    cfg = _cfg(tmp_path)
    with pytest.raises(RuntimeError, match="no LSEG fundamental data fetched"):
        fetch_fundamentals(cfg)
    assert not store.cache_path(tmp_path / "fund", "AAPL.O", url_quote=True).exists()


def test_fetch_fundamentals_no_values_does_not_cache(tmp_path, monkeypatch):
    ld = _FakeLD(no_values=True)
    monkeypatch.setattr(lseg, "session", lambda: nullcontext(ld))
    monkeypatch.setattr(lseg, "resolve_permids", lambda ld, permids: {})
    cfg = _cfg(tmp_path)
    with pytest.raises(RuntimeError, match="no LSEG fundamental data fetched"):
        fetch_fundamentals(cfg)
    assert not store.cache_path(tmp_path / "fund", "AAPL.O", url_quote=True).exists()


def test_step_registered():
    step = next(s for s in pipeline.STEPS if s.name == "lseg-fundamentals")
    assert step.phase == "fetch"
    assert step.per_item is True
    assert step.outs == ("lseg.fundamentals_out",)
