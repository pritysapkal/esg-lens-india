"""Checks against manually downloaded NSE files. Skipped automatically when data is absent.

Real filings are never committed (NSE terms of use), so these only run on a machine where the
files were downloaded by hand into data/raw/.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ingestion import config
from ingestion.instance import count_instance, read_header
from ingestion.intake import read_manifest
from ingestion.parse_xbrl import parse_instance, summarise
from ingestion.taxonomy import find_taxonomies

pytestmark = pytest.mark.realdata

HDFC_FILE = "BRSR_797_WebXMLFile_20260911_195404900.xml"
EXPECTED_TAXONOMIES = ["2021-09-30", "2023-06-30", "2024-04-30", "2025-05-31", "2026-02-28"]


@pytest.fixture(scope="module")
def hdfc_xml() -> Path:
    candidates = [config.XBRL_INBOX_DIR / HDFC_FILE, *config.XBRL_DIR.rglob(HDFC_FILE)]
    found = [p for p in candidates if p.is_file()]
    if not found:
        pytest.skip(f"{HDFC_FILE} not present (download manually, see docs/how_to_add_filings.md)")
    return found[0]


def test_hdfc_header(hdfc_xml: Path) -> None:
    header = read_header(hdfc_xml)
    assert header.isin == "INE040A01034"
    assert header.taxonomy_version == "2026-02-28"


def test_hdfc_counts(hdfc_xml: Path) -> None:
    counts = count_instance(hdfc_xml)
    assert (counts.facts, counts.concepts, counts.contexts, counts.units) == (2182, 618, 658, 11)


def test_all_taxonomy_versions_found() -> None:
    if not any(config.TAXONOMY_DIR.rglob("*.xsd")):
        pytest.skip("no taxonomy packages under data/raw/taxonomy")
    df = find_taxonomies(xml_dirs=())
    assert df["version"].tolist() == EXPECTED_TAXONOMIES
    assert (df["path_to_entry_xsd"] != "").all()


# --- parser (ingestion.parse_xbrl) ------------------------------------------------------------


def _parse_manifest_filing(symbol: str, year: str):
    manifest = read_manifest()
    rows = manifest[(manifest["symbol"] == symbol) & (manifest["reporting_year_label"] == year)]
    if rows.empty or not (config.REPO_ROOT / rows.iloc[0]["path"]).is_file():
        pytest.skip(f"{symbol} {year} not in the intake store")
    filing = rows.iloc[0].to_dict()
    parsed = parse_instance(config.REPO_ROOT / filing["path"], filing["filing_id"])
    return parsed, summarise(parsed, filing, 0.0)


def test_hdfc_parsed(hdfc_xml: Path) -> None:
    parsed = parse_instance(hdfc_xml, "hdfc")
    facts = parsed.facts + parsed.text_facts
    assert len(facts) == 2182
    assert len({(f["namespace"], f["concept"]) for f in facts}) == 618
    assert (len(parsed.contexts), len(parsed.units)) == (658, 11)

    summary = summarise(parsed, {"filing_id": "hdfc", "symbol": "", "isin": "", "path": ""}, 0.0)
    assert (summary["period_start"], summary["period_end"]) == (date(2025, 4, 1), date(2026, 3, 31))
    assert summary["period_months"] == 12

    no_dims = {c["context_id"] for c in parsed.contexts if c["dimension_key"] == ""}
    current = {
        f["concept"]: f["raw_value"]
        for f in parsed.facts
        if f["context_ref"] == summary["main_context_id"] and f["context_ref"] in no_dims
    }
    assert current["TotalScope1Emissions"] == "91849.5"
    assert current["TotalScope2Emissions"] == "236495.41"
    assert current["PercentageOfGrossWagesPaidToFemaleToTotalWagesPaid"] == "0.2036"


def test_nestle_15_month_period() -> None:
    _, summary = _parse_manifest_filing("NESTLEIND", "2023-2024")
    assert (summary["period_start"], summary["period_end"]) == (date(2023, 1, 1), date(2024, 3, 31))
    assert summary["period_months"] == 15
    assert summary["is_non_standard_period"] is True
