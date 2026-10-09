"""Header and count extraction on the synthetic instance."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.instance import (
    InstanceError,
    count_instance,
    read_header,
    taxonomy_version_from_href,
)


def test_read_header(synthetic_xml: Path) -> None:
    header = read_header(synthetic_xml)
    assert header.isin == "INE000X00000"
    assert header.identifier_scheme == "ISIN"
    assert header.taxonomy_version == "2026-02-28"


def test_cin_scheme_has_no_isin(synthetic_xml: Path, tmp_path: Path) -> None:
    text = synthetic_xml.read_text(encoding="utf-8")
    text = text.replace("in-capmkt/ISIN", "in-capmkt/CorporateIdentityNumber")
    text = text.replace(">INE000X00000<", ">L00000XX2000PLC000000<")
    cin = tmp_path / "cin.xml"
    cin.write_text(text, encoding="utf-8")

    header = read_header(cin)
    assert header.identifier == "L00000XX2000PLC000000"
    assert header.identifier_scheme == "CorporateIdentityNumber"
    assert header.isin is None


def test_count_instance(synthetic_xml: Path) -> None:
    counts = count_instance(synthetic_xml)
    assert counts.facts == 14
    assert counts.concepts == 11
    assert counts.contexts == 6
    assert counts.units == 4
    assert counts.nil_facts == 1


@pytest.mark.parametrize(
    ("href", "version"),
    [
        ("in-capmkt-ent-2021-09-30.xsd", "2021-09-30"),
        ("https://www.sebi.gov.in/xbrl/BRSR/in-capmkt-ent-2024-04-30.xsd", "2024-04-30"),
        ("in-capmkt-2026-02-28.xsd", None),
    ],
)
def test_taxonomy_version_from_href(href: str, version: str | None) -> None:
    assert taxonomy_version_from_href(href) == version


def test_read_header_rejects_non_xbrl(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<root/>", encoding="utf-8")
    with pytest.raises(InstanceError):
        read_header(bad)
