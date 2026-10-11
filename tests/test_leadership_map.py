"""The Leadership indicator seed comes from the taxonomy, not from guesses."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

from ingestion import config

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "dbt" / "seeds" / "leadership_indicator_map.csv"


def _module():
    spec = importlib.util.spec_from_file_location(
        "build_leadership_map", ROOT / "scripts" / "build_leadership_map.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows() -> list[dict[str, str]]:
    with SEED.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_seed_has_every_principle_in_every_taxonomy_version():
    by_version: dict[str, set[str]] = {}
    for row in _rows():
        by_version.setdefault(row["taxonomy_version"], set()).add(row["principle"])
    assert len(by_version) == 5
    for version, principles in by_version.items():
        assert principles == {f"Principle{n}" for n in range(1, 10)}, version


def test_seed_has_no_helper_elements():
    module = _module()
    for row in _rows():
        assert not module.NOT_AN_ANSWER.search(row["concept"]), row["concept"]
        assert not row["concept"].endswith(("Abstract", "Table", "Axis", "Member")), row["concept"]


def test_number_of_indicators_is_close_to_the_brsr_format():
    # SEBI's format has about 42 Leadership indicators; the taxonomy splits a few into parts.
    indicators: dict[str, set[tuple[str, str]]] = {}
    for row in _rows():
        indicators.setdefault(row["taxonomy_version"], set()).add(
            (row["principle"], row["indicator"])
        )
    for version, found in indicators.items():
        assert 40 <= len(found) <= 50, (version, len(found))


def test_seed_is_generated_from_the_taxonomy():
    if not any(config.TAXONOMY_DIR.rglob("in-capmkt-pre-*.xml")):
        pytest.skip("no taxonomy packages under data/raw/taxonomy")
    assert _module().main(["--check"]) == 0, "run: python scripts/build_leadership_map.py"
