"""XBRL parser on the synthetic instance (no real data needed)."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from ingestion.parse_xbrl import (
    TABLES,
    parse_all,
    parse_instance,
    period_months,
    unit_label,
)

FILING_ID = "f" * 64


@pytest.fixture(scope="module")
def parsed(synthetic_xml: Path):
    return parse_instance(synthetic_xml, FILING_ID)


def _by_id(rows: list[dict], key: str) -> dict[str, dict]:
    return {row[key]: row for row in rows}


# --- contexts -------------------------------------------------------------------------------


def test_duration_and_instant_contexts(parsed) -> None:
    ctx = _by_id(parsed.contexts, "context_id")
    assert len(ctx) == 6
    main = ctx["DCYMain"]
    assert main["period_type"] == "duration"
    assert (main["start_date"], main["end_date"]) == (date(2025, 4, 1), date(2026, 3, 31))
    assert main["instant_date"] is None
    assert main["identifier_scheme"] == "https://www.sebi.gov.in/in-capmkt/ISIN"
    assert main["identifier_value"] == "INE000X00000"
    assert main["dimensions"] == "[]"
    assert main["dimension_key"] == ""

    inst = ctx["ICYMain"]
    assert inst["period_type"] == "instant"
    assert inst["instant_date"] == date(2026, 3, 31)
    assert inst["start_date"] is None and inst["end_date"] is None


def test_explicit_dimensions_sorted_by_axis(parsed) -> None:
    ctx = _by_id(parsed.contexts, "context_id")["ICYMaleEmployees"]
    # Filed as GenderAxis then EmployeesAndWorkersAxis; the key is sorted by axis.
    assert ctx["dimension_key"] == "EmployeesAndWorkersAxis=EmployeesMember|GenderAxis=MaleMember"
    assert json.loads(ctx["dimensions"]) == [
        {
            "axis": "in-capmkt:EmployeesAndWorkersAxis",
            "member": "in-capmkt:EmployeesMember",
            "member_type": "explicit",
        },
        {
            "axis": "in-capmkt:GenderAxis",
            "member": "in-capmkt:MaleMember",
            "member_type": "explicit",
        },
    ]


def test_typed_dimension(parsed) -> None:
    ctx = _by_id(parsed.contexts, "context_id")["D_AssuranceProvider1"]
    assert json.loads(ctx["dimensions"]) == [
        {
            "axis": "in-capmkt:AssessmentOrAssuranceProviderAxis",
            "member": "Provider1",
            "member_type": "typed",
        }
    ]
    assert ctx["dimension_key"] == "AssessmentOrAssuranceProviderAxis=Provider1"


# --- units ----------------------------------------------------------------------------------


def test_units_incl_divide(parsed) -> None:
    units = _by_id(parsed.units, "unit_id")
    assert set(units) == {"INR", "pure", "tCO2e", "tCO2ePerINR"}
    assert units["INR"]["numerator_measures"] == ["iso4217:INR"]
    assert units["INR"]["denominator_measures"] == []
    assert units["INR"]["unit_label"] == "INR"
    divide = units["tCO2ePerINR"]
    assert divide["numerator_measures"] == ["in-capmkt:tCO2e"]
    assert divide["denominator_measures"] == ["iso4217:INR"]
    assert divide["unit_label"] == "tCO2e/INR"


def test_unit_label_multiple_measures() -> None:
    assert unit_label(["a:kg", "a:m"], ["b:s", "b:s"]) == "kg*m/s*s"


# --- facts ----------------------------------------------------------------------------------


def test_fact_counts_and_split(parsed) -> None:
    assert len(parsed.facts) + len(parsed.text_facts) == 14
    assert {r["concept"] for r in parsed.text_facts} == {
        "DetailsOfMaterialIssuesExplanatoryTextBlock",  # short, but a TextBlock
        "PolicyDetailsExplanatoryTextBlock",  # long TextBlock
    }
    assert all(r["concept"] != "NameOfTheCompany" for r in parsed.text_facts)
    # sequence covers both tables in file order
    seqs = sorted(r["sequence"] for r in parsed.facts + parsed.text_facts)
    assert seqs == list(range(1, 15))


def test_long_non_textblock_goes_to_text_facts(synthetic_xml: Path, tmp_path: Path) -> None:
    text = synthetic_xml.read_text(encoding="utf-8")
    long_value = "x" * 1001
    text = text.replace(">Example Ltd<", f">{long_value}<")
    path = tmp_path / "long.xml"
    path.write_text(text, encoding="utf-8")
    result = parse_instance(path, FILING_ID)
    row = next(r for r in result.text_facts if r["concept"] == "NameOfTheCompany")
    assert row["raw_value"] == long_value


def test_text_block_keeps_full_text(parsed) -> None:
    row = next(r for r in parsed.text_facts if r["concept"] == "PolicyDetailsExplanatoryTextBlock")
    assert row["raw_value"].startswith("<p>Synthetic policy text")
    assert row["raw_value"].endswith("</p>")
    assert len(row["raw_value"]) > 1000


def test_raw_value_is_never_cast(parsed) -> None:
    facts = {(r["concept"], r["context_ref"]): r for r in parsed.facts}
    tiny = facts[("TotalScope1EmissionsPerRupeeOfTurnover", "DCYMain")]
    assert tiny["raw_value"] == "0.0000000888"
    assert isinstance(tiny["raw_value"], str)
    assert tiny["decimals"] == "INF"
    assert facts[("TotalScope1Emissions", "DPYMain")]["raw_value"] == "11111.10"  # trailing 0 kept


def test_nil_fact(parsed) -> None:
    nil = next(r for r in parsed.facts if r["concept"] == "TotalScope3Emissions")
    assert nil["is_nil"] is True
    assert nil["raw_value"] is None
    assert nil["is_numeric"] is True
    assert sum(r["is_nil"] for r in parsed.facts + parsed.text_facts) == 1


def test_numeric_flag_and_qname(parsed) -> None:
    rows = _by_id(parsed.facts, "concept")
    assert rows["PaidUpCapital"]["is_numeric"] is True
    assert rows["PaidUpCapital"]["unit_ref"] == "INR"
    assert rows["NameOfTheCompany"]["is_numeric"] is False
    assert rows["NameOfTheCompany"]["unit_ref"] is None
    assert rows["NameOfTheCompany"]["prefix"] == "in-capmkt"
    assert (
        rows["NameOfTheCompany"]["namespace"] == "https://www.sebi.gov.in/xbrl/2026-02-28/in-capmkt"
    )


def test_fact_ids_unique_and_stable(synthetic_xml: Path, parsed) -> None:
    ids = [r["fact_id"] for r in parsed.facts + parsed.text_facts]
    assert len(set(ids)) == len(ids)
    again = parse_instance(synthetic_xml, FILING_ID)
    assert [r["fact_id"] for r in again.facts] == [r["fact_id"] for r in parsed.facts]


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_bom_and_encodings(synthetic_xml: Path, tmp_path: Path, encoding: str, parsed) -> None:
    text = synthetic_xml.read_text(encoding="utf-8")
    if encoding == "utf-16":
        text = text.replace('encoding="UTF-8"', 'encoding="UTF-16"')
    path = tmp_path / f"{encoding}.xml"
    path.write_bytes(text.encode(encoding))
    result = parse_instance(path, FILING_ID)
    assert result.facts == parsed.facts
    assert result.text_facts == parsed.text_facts


# --- filing summary + period ----------------------------------------------------------------


def test_period_months() -> None:
    assert period_months(365) == 12
    assert period_months(366) == 12
    assert period_months(456) == 15  # 2023-01-01..2024-03-31
    assert period_months(275) == 9


# --- end to end: manifest -> Parquet --------------------------------------------------------


def _manifest(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "manifest.csv"
    cols = ["filing_id", "symbol", "isin", "reporting_year_label", "taxonomy_version", "path"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(path: Path, filing_id: str = FILING_ID, symbol: str = "EXAMPLE") -> dict:
    return {
        "filing_id": filing_id,
        "symbol": symbol,
        "isin": "INE000X00000",
        "reporting_year_label": "2025-2026",
        "taxonomy_version": "2026-02-28",
        "path": str(path),
    }


def _files(out: Path) -> dict[str, float]:
    return {p.relative_to(out).as_posix(): p.stat().st_mtime_ns for p in out.rglob("*.parquet")}


def test_parse_all_writes_partitioned_parquet(synthetic_xml: Path, tmp_path: Path) -> None:
    out, errors = tmp_path / "parsed", tmp_path / "parse_errors.csv"
    summary = parse_all(_manifest(tmp_path, [_row(synthetic_xml)]), out, errors)
    assert len(summary.parsed) == 1 and not summary.failed

    for table in TABLES:
        assert (out / table / "reporting_year_label=2025-2026" / f"{FILING_ID}.parquet").is_file()
    filing = pq.read_table(out / "filings").to_pylist()[0]
    assert filing["reporting_year_label"] == "2025-2026"  # hive partition column
    assert (filing["n_facts"], filing["n_text"], filing["n_nil"]) == (14, 2, 1)
    assert (filing["n_contexts"], filing["n_units"], filing["n_concepts"]) == (6, 4, 11)
    assert filing["n_numeric"] == 9
    assert filing["n_dimension_axes"] == 3
    assert filing["main_context_id"] == "DCYMain"
    assert (filing["period_start"], filing["period_end"]) == (date(2025, 4, 1), date(2026, 3, 31))
    assert (filing["period_days"], filing["period_months"]) == (365, 12)
    assert filing["is_non_standard_period"] is False
    assert filing["taxonomy_version"] == "2026-02-28"

    facts_file = out / "facts" / "reporting_year_label=2025-2026" / f"{FILING_ID}.parquet"
    assert str(pq.read_schema(facts_file).field("raw_value").type) == "string"
    facts = pd.read_parquet(out / "facts")
    assert "0.0000000888" in set(facts["raw_value"])


def test_rerun_is_idempotent_and_only_touches_reparsed(synthetic_xml: Path, tmp_path: Path) -> None:
    other_id = "e" * 64
    manifest = _manifest(
        tmp_path, [_row(synthetic_xml), _row(synthetic_xml, filing_id=other_id, symbol="OTHER")]
    )
    out, errors = tmp_path / "parsed", tmp_path / "parse_errors.csv"
    parse_all(manifest, out, errors)
    first = _files(out)
    first_facts = pd.read_parquet(out / "facts").sort_values(["filing_id", "sequence"])

    parse_all(manifest, out, errors, only="example")  # re-parse one filing only
    second = _files(out)
    assert set(second) == set(first)
    for name, mtime in second.items():
        if other_id in name:
            assert mtime == first[name], f"{name} was rewritten"
    again = pd.read_parquet(out / "facts").sort_values(["filing_id", "sequence"])
    pd.testing.assert_frame_equal(first_facts.reset_index(drop=True), again.reset_index(drop=True))
    assert len(again) == 2 * 12


def test_bad_file_is_logged_and_run_continues(synthetic_xml: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<xbrli:xbrl xmlns:xbrli='http://www.xbrl.org/2003/instance'><oops", "utf-8")
    missing = tmp_path / "missing.xml"
    rows = [
        _row(bad, filing_id="b" * 64, symbol="BAD"),
        _row(missing, filing_id="c" * 64, symbol="MISSING"),
        _row(synthetic_xml),
    ]
    out, errors = tmp_path / "parsed", tmp_path / "parse_errors.csv"
    summary = parse_all(_manifest(tmp_path, rows), out, errors)

    assert [r["symbol"] for r in summary.parsed] == ["EXAMPLE"]
    logged = pd.read_csv(errors, dtype=str)
    assert logged["symbol"].tolist() == ["BAD", "MISSING"]
    assert logged["error_type"].tolist() == ["InstanceError", "FileNotFoundError"]
    assert not list(out.rglob(f"{'b' * 64}.parquet"))

    # Fix the bad file: its error row disappears on the next run, others are kept.
    bad.write_bytes(synthetic_xml.read_bytes())
    parse_all(_manifest(tmp_path, rows), out, errors, only="BAD")
    assert pd.read_csv(errors, dtype=str)["symbol"].tolist() == ["MISSING"]


def test_limit(synthetic_xml: Path, tmp_path: Path) -> None:
    rows = [_row(synthetic_xml, filing_id=c * 64, symbol=c.upper()) for c in "abc"]
    summary = parse_all(_manifest(tmp_path, rows), tmp_path / "out", tmp_path / "err.csv", limit=2)
    assert [r["symbol"] for r in summary.parsed] == ["A", "B"]
