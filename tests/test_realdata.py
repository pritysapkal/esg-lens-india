"""Checks against manually downloaded NSE files. Skipped automatically when data is absent.

Real filings are never committed (NSE terms of use), so these only run on a machine where the
files were downloaded by hand into data/raw/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion import config
from ingestion.instance import count_instance, read_header
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
