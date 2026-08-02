"""Parsing checks for financialdatadb xlsx sources (require raw data present)."""

from pathlib import Path

import pytest

from factor_weaver.data.financialdatadb import (
    _COMPANY_COLUMNS,
    _SECTIONS,
    _parse_companies_file,
    _parse_fundamentals_file,
)
from factor_weaver.data.tickers import normalize_ticker

_RAW_DIR = Path("data/raw/financialdatadb/us_financials")


def test_normalize_ticker() -> None:
    assert normalize_ticker("BRK-B") == "BRK.B"
    assert normalize_ticker("brk-b") == "BRK.B"
    assert normalize_ticker("BAC-PA") == "BAC.PA"
    assert normalize_ticker("BF/B") == "BF.B"
    assert normalize_ticker(" AAPL ") == "AAPL"
    assert normalize_ticker(None) is None


def test_parse_fundamentals_sheet() -> None:
    path = _RAW_DIR / "A_tickers.xlsx"
    if not path.exists():
        pytest.skip("raw data not present")
    df = _parse_fundamentals_file(path, sheet_names=["A"])
    assert list(df.columns) == ["ticker", "date", "section", "field", "value"]
    assert bool(df["ticker"].eq("A").all())
    assert bool(df["section"].isin(_SECTIONS).all())
    assert bool(df["value"].notna().all())
    assert bool(df["date"].notna().all())
    assert not df.duplicated(subset=["ticker", "date", "section", "field"]).any()
    assert (df[df.section.eq("Valuation Measures")].field == "Market Capitalization").any()
    assert len(df) > 100


def test_parse_fundamentals_normalizes_tickers() -> None:
    path = _RAW_DIR / "B_tickers.xlsx"
    if not path.exists():
        pytest.skip("raw data not present")
    df = _parse_fundamentals_file(path, sheet_names=["BRK-B"])
    assert bool(df["ticker"].eq("BRK.B").all())


def test_parse_companies() -> None:
    path = _RAW_DIR / "_US_listed_companies.xlsx"
    if not path.exists():
        pytest.skip("raw data not present")
    companies = _parse_companies_file(path)
    assert list(companies.columns) == list(_COMPANY_COLUMNS)
    assert len(companies) > 5000
    assert "A" in set(companies["ticker"])
    assert "BRK.B" in set(companies["ticker"])
    assert bool((companies["sector"].notna().sum() > 5000))
