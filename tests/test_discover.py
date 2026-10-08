"""Listing CSV normalisation (synthetic fixture only)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from ingestion.discover import (
    LISTING_COLUMNS,
    filing_id_from_url,
    load_listings,
    normalise_header,
    parse_nse_date,
    read_listing_csv,
    symbol_from_filename,
)
from ingestion.universe import load_universe, snake_case


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("COMPANY \n", "COMPANY"),
        ("**XBRL \n", "XBRL"),
        ("ORIGINAL SUBMISSION DATE \n", "ORIGINAL SUBMISSION DATE"),
        ("  LATEST  REVISION DATE ", "LATEST REVISION DATE"),
    ],
)
def test_normalise_header(raw: str, expected: str) -> None:
    assert normalise_header(raw) == expected


def test_parse_nse_date() -> None:
    assert parse_nse_date("05-Oct-2026") == date(2026, 10, 5)
    assert parse_nse_date(" 29-jun-2024 ") == date(2024, 6, 29)


@pytest.mark.parametrize("value", ["-", "", " - ", None])
def test_parse_nse_date_dash_is_null(value) -> None:
    assert parse_nse_date(value) is None


def test_parse_nse_date_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_nse_date("2026-10-05")


@pytest.mark.parametrize(
    ("name", "symbol"),
    [
        ("CF-BRSR-equities-HDFCBANK-01-04-2023-to-08-10-2026.csv", "HDFCBANK"),
        ("CF-BRSR-equities-M&M-01-04-2023-to-08-10-2026.csv", "M&M"),
        ("CF-BRSR-equities-BAJAJ-AUTO-01-04-2023-to-08-10-2026.csv", "BAJAJ-AUTO"),
    ],
)
def test_symbol_from_filename(name: str, symbol: str) -> None:
    assert symbol_from_filename(name) == symbol


def test_symbol_from_filename_rejects_other_files() -> None:
    with pytest.raises(ValueError):
        symbol_from_filename("ind_nifty50list.csv")


def test_read_listing_csv(listing_sample_csv: Path) -> None:
    df = read_listing_csv(listing_sample_csv, symbol="EXAMPLE")
    assert list(df.columns) == LISTING_COLUMNS
    assert len(df) == 3
    first = df.iloc[0]
    assert first["company_name"] == "Example Ltd"
    assert first["reporting_year_label"] == "2025-2026"
    assert first["submission_date"] == date(2026, 10, 5)
    assert first["revision_date"] is None
    assert first["xbrl_file_name"] == "BRSR_EXAMPLE_2026_WEB.xml"
    assert first["filing_id"] == filing_id_from_url(first["xbrl_url"])
    assert df.iloc[1]["revision_date"] == date(2025, 8, 20)
    assert df["is_non_standard_period"].tolist() == [False, False, True]


def test_load_listings_symbol_from_name_and_dedup(listing_sample_csv: Path, tmp_path: Path) -> None:
    shutil.copy(listing_sample_csv, tmp_path / "CF-BRSR-equities-M&M-01-04-2023-to-08-10-2026.csv")
    # Same filings saved again under another download window -> de-duplicated on xbrl_url.
    shutil.copy(listing_sample_csv, tmp_path / "CF-BRSR-equities-M&M-01-04-2022-to-08-10-2026.csv")
    df = load_listings(tmp_path)
    assert len(df) == 3
    assert set(df["symbol"]) == {"M&M"}
    assert df["xbrl_url"].is_unique


def test_load_universe_snake_case(tmp_path: Path) -> None:
    csv = tmp_path / "ind_nifty50list.csv"
    csv.write_text(
        "Company Name,Industry,Symbol,Series,ISIN Code\n"
        "Example Ltd.,Services,EXAMPLE,EQ,INE000X00000\n",
        encoding="utf-8",
    )
    df = load_universe(csv)
    assert list(df.columns) == ["company_name", "industry", "symbol", "series", "isin_code"]
    assert snake_case("ISIN Code") == "isin_code"
