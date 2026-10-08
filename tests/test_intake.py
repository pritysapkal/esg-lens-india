"""Intake moves, never overwrites and is idempotent (tmp dirs + synthetic data only)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from ingestion.discover import read_listing_csv
from ingestion.intake import MANIFEST_COLUMNS, intake, read_manifest, sha256_file
from ingestion.todo import RECEIVED, build_report, filing_status

FILE_2026 = "BRSR_EXAMPLE_2026_WEB.xml"
FILE_2025 = "BRSR_EXAMPLE_2025_WEB.xml"
NO_UNIVERSE = pd.DataFrame(columns=["company_name", "industry", "symbol", "series", "isin_code"])


def cin_scheme_copy(synthetic_xml: Path, dest: Path, identifier: str) -> None:
    """Write the synthetic instance with a CIN-scheme identifier, like pre-2026 filings."""
    text = synthetic_xml.read_text(encoding="utf-8")
    text = text.replace("in-capmkt/ISIN", "in-capmkt/CorporateIdentityNumber")
    text = text.replace(">INE000X00000<", f">{identifier}<")
    dest.write_text(text, encoding="utf-8")


@pytest.fixture
def env(tmp_path: Path, listing_sample_csv: Path, synthetic_xml: Path) -> dict:
    dirs = {name: tmp_path / name for name in ("inbox", "xbrl", "taxonomy")}
    for d in dirs.values():
        d.mkdir()
    (dirs["taxonomy"] / "2026-02-28").mkdir()
    shutil.copy(synthetic_xml, dirs["inbox"] / FILE_2026)
    other = synthetic_xml.read_text(encoding="utf-8").replace("Example Ltd", "Other Ltd")
    (dirs["inbox"] / "not_in_listing.xml").write_text(other, encoding="utf-8")
    return {
        "inbox_dir": dirs["inbox"],
        "xbrl_dir": dirs["xbrl"],
        "taxonomy_dir": dirs["taxonomy"],
        "manifest_path": tmp_path / "manifest.csv",
        "listing": read_listing_csv(listing_sample_csv, symbol="EXAMPLE"),
        "universe": NO_UNIVERSE,
    }


def test_intake_moves_matched_file(env: dict, synthetic_xml: Path) -> None:
    result = intake(**env)

    dest = env["xbrl_dir"] / "INE000X00000" / "2025-2026" / FILE_2026
    assert dest.is_file()
    assert not (env["inbox_dir"] / FILE_2026).exists()
    assert sha256_file(dest) == sha256_file(synthetic_xml)
    assert [name for name, _ in result.unmatched] == ["not_in_listing.xml"]
    assert (env["inbox_dir"] / "not_in_listing.xml").exists()
    assert result.warnings == []

    manifest = read_manifest(env["manifest_path"])
    assert list(manifest.columns) == MANIFEST_COLUMNS
    assert len(manifest) == 1
    row = manifest.iloc[0]
    assert row["symbol"] == "EXAMPLE"
    assert row["isin"] == "INE000X00000"
    assert row["taxonomy_version"] == "2026-02-28"
    assert row["reporting_year_label"] == "2025-2026"
    assert row["matched_listing"] == "True"
    assert row["entity_identifier_scheme"] == "ISIN"
    assert row["isin_source"] == "xbrl"


def _tree(env: dict) -> list[Path]:
    return sorted(env["xbrl_dir"].rglob("*")) + sorted(env["inbox_dir"].rglob("*"))


def test_intake_is_idempotent(env: dict) -> None:
    intake(**env)
    manifest_before = env["manifest_path"].read_bytes()
    files_before = _tree(env)

    second = intake(**env)

    assert second.moved == []
    assert env["manifest_path"].read_bytes() == manifest_before
    assert _tree(env) == files_before


def test_identical_redrop_is_reported_not_filed(env: dict, synthetic_xml: Path) -> None:
    intake(**env)
    shutil.copy(synthetic_xml, env["inbox_dir"] / FILE_2026)
    result = intake(**env)
    assert result.moved == []
    assert result.duplicates == [FILE_2026]
    assert len(read_manifest(env["manifest_path"])) == 1


def test_same_name_different_content_keeps_both(env: dict, synthetic_xml: Path) -> None:
    intake(**env)
    changed = synthetic_xml.read_text(encoding="utf-8").replace("1200", "1201")
    (env["inbox_dir"] / FILE_2026).write_text(changed, encoding="utf-8")

    result = intake(**env)

    dest_dir = env["xbrl_dir"] / "INE000X00000" / "2025-2026"
    names = sorted(p.name for p in dest_dir.iterdir())
    sha = result.moved[0]["sha256"]
    assert names == [FILE_2026, f"BRSR_EXAMPLE_2026_WEB__{sha[:8]}.xml"]
    assert len(read_manifest(env["manifest_path"])) == 2


def test_warns_when_taxonomy_folder_missing(env: dict) -> None:
    shutil.rmtree(env["taxonomy_dir"] / "2026-02-28")
    result = intake(**env)
    assert len(result.moved) == 1
    assert any("2026-02-28" in w for w in result.warnings)


def test_cin_scheme_filing_gets_isin_from_same_symbol(env: dict, synthetic_xml: Path) -> None:
    cin_scheme_copy(synthetic_xml, env["inbox_dir"] / FILE_2025, "L00000XX2000PLC000000")
    result = intake(**env)

    rows = {row["file_name"]: row for row in result.moved}
    assert rows[FILE_2025]["isin"] == "INE000X00000"
    assert rows[FILE_2025]["isin_source"] == "xbrl_same_symbol"
    assert rows[FILE_2025]["entity_identifier"] == "L00000XX2000PLC000000"
    assert rows[FILE_2025]["entity_identifier_scheme"] == "CorporateIdentityNumber"
    assert (env["xbrl_dir"] / "INE000X00000" / "2024-2025" / FILE_2025).is_file()


def test_dummy_identifier_falls_back_to_universe(env: dict, synthetic_xml: Path) -> None:
    (env["inbox_dir"] / FILE_2026).unlink()
    cin_scheme_copy(synthetic_xml, env["inbox_dir"] / FILE_2025, "A00000AA0000AAA000000")
    universe = NO_UNIVERSE.copy()
    universe.loc[0] = ["Example Ltd", "Services", "EXAMPLE", "EQ", "INE000X00001"]

    result = intake(**{**env, "universe": universe})

    assert [(r["isin"], r["isin_source"]) for r in result.moved] == [("INE000X00001", "universe")]


def test_unresolvable_isin_stays_in_inbox(env: dict, synthetic_xml: Path) -> None:
    (env["inbox_dir"] / FILE_2026).unlink()
    cin_scheme_copy(synthetic_xml, env["inbox_dir"] / FILE_2025, "A00000AA0000AAA000000")
    result = intake(**env)
    assert result.moved == []
    assert "cannot resolve ISIN" in dict(result.unmatched)[FILE_2025]
    assert (env["inbox_dir"] / FILE_2025).exists()


def test_status_report(env: dict) -> None:
    intake(**env)
    manifest = read_manifest(env["manifest_path"])
    status = filing_status(env["listing"], manifest)
    assert (status["status"] == RECEIVED).sum() == 1

    universe = pd.DataFrame(
        {"company_name": ["Other Ltd"], "industry": ["Services"], "symbol": ["OTHER"]}
    )
    report = build_report(env["listing"], universe, manifest)
    assert "| Listed filings | 3 |" in report
    assert "| Received (in manifest) | 1 |" in report
    assert "| EXAMPLE | Example Ltd | **no** |" in report
    assert "| OTHER | Other Ltd | Services |" in report
