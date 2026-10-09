"""Consistency of the committed metric catalogue seeds with docs/metric_shortlist.csv (no data)."""

from __future__ import annotations

import csv
from collections import defaultdict

import pytest

from ingestion import config

SEEDS = config.DBT_DIR / "seeds"
# Units that old taxonomies file as 'pure' for quantities: resolved by int_implied_units instead.
PURE_IS_A_REAL_UNIT = {"pct", "count", "per_million_hours"}


def _read(path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def catalogue() -> list[dict]:
    return _read(SEEDS / "concept_metric_map.csv")


@pytest.fixture(scope="module")
def shortlist() -> list[dict]:
    return _read(config.DOCS_DIR / "metric_shortlist.csv")


def test_every_kept_shortlist_concept_is_mapped(catalogue, shortlist) -> None:
    mapped = {row["concept"] for row in catalogue}
    kept = {row["concept"] for row in shortlist if row["role"] != "dropped"}
    assert kept - mapped == set()


def test_dropped_concepts_are_not_mapped(catalogue, shortlist) -> None:
    mapped = {row["concept"] for row in catalogue}
    dropped = {row["concept"] for row in shortlist if row["role"] == "dropped"}
    assert dropped & mapped == set()


def test_roles_match_shortlist(catalogue, shortlist) -> None:
    roles = {row["concept"]: row["role"] for row in shortlist}
    for row in catalogue:
        if row["concept"] in roles:
            assert row["role"] == roles[row["concept"]], row["concept"]


def test_metric_attributes_consistent_across_versions(catalogue) -> None:
    seen: dict[str, set] = defaultdict(set)
    for row in catalogue:
        seen[row["metric_id"]].add((row["unit_std"], row["role"], row["direction"]))
    assert {m: v for m, v in seen.items() if len(v) > 1} == {}


def test_one_row_per_version_and_concept(catalogue) -> None:
    keys = [(row["taxonomy_version"], row["concept"]) for row in catalogue]
    assert len(keys) == len(set(keys))


def test_known_renames_mapped_to_successor_metric(catalogue) -> None:
    by_concept = defaultdict(set)
    for row in catalogue:
        by_concept[row["concept"]].add(row["metric_id"])
    assert by_concept["TotalEnergyConsumption"] == {"energy_total_gj"}
    assert by_concept["TotalScope1AndScope2EmissionsPerRupeeOfTurnover"] == {
        "ghg_intensity_filed_tco2e_per_inr_cr"
    }


def test_every_filed_unit_has_a_conversion(catalogue) -> None:
    units = _read(SEEDS / "unit_normalisation.csv")
    conversions = {(r["unit_label_raw"], r["unit_std"]) for r in units}
    missing = set()
    for row in catalogue:
        if row["value_kind"] != "numeric":
            continue
        for label in filter(None, row["unit_raw_expected"].split("|")):
            if label == "pure" and row["unit_std"] not in PURE_IS_A_REAL_UNIT:
                continue  # old-taxonomy quantity: unit inferred in int_implied_units
            if (label, row["unit_std"]) not in conversions:
                missing.add((label, row["unit_std"]))
    assert missing == set()


def test_text_units_point_to_known_labels() -> None:
    labels = {r["unit_label_raw"] for r in _read(SEEDS / "unit_normalisation.csv")}
    for row in _read(SEEDS / "text_unit_normalisation.csv"):
        assert row["unit_label"] in labels, row
        assert row["unit_text"] == " ".join(row["unit_text"].lower().split()), row
