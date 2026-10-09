"""DuckDB raw load from parsed Parquet (synthetic data)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from ingestion.load_raw import load_raw
from ingestion.parse_xbrl import parse_instance, write_parquet


def test_load_raw_creates_tables(synthetic_xml: Path, tmp_path: Path) -> None:
    parsed_dir, db = tmp_path / "parsed", tmp_path / "wh.duckdb"
    parsed = parse_instance(synthetic_xml, "f" * 64)
    parsed.filings = [{"filing_id": "f" * 64, "symbol": "EXAMPLE", "n_facts": 14}]
    write_parquet(parsed, "f" * 64, "2025-2026", parsed_dir)

    counts = load_raw(parsed_dir, db)
    assert counts == {"filings": 1, "contexts": 6, "units": 4, "facts": 12, "text_facts": 2}
    with duckdb.connect(str(db), read_only=True) as con:
        year, raw = con.execute(
            "select reporting_year_label, raw_value from raw_facts "
            "where concept = 'TotalScope1EmissionsPerRupeeOfTurnover'"
        ).fetchone()
    assert (year, raw) == ("2025-2026", "0.0000000888")

    load_raw(parsed_dir, db)  # create or replace: re-running does not duplicate rows
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute("select count(*) from raw_facts").fetchone()[0] == 12


def test_load_raw_without_parquet(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_raw(tmp_path / "parsed", tmp_path / "wh.duckdb")
