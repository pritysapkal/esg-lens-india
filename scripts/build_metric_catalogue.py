"""Build the metric catalogue seed and the metric definitions page.

    python scripts/build_metric_catalogue.py              # seed + docs (needs local data)
    python scripts/build_metric_catalogue.py --docs-only  # docs from the committed seed

Inputs: docs/metric_shortlist.csv (analytics-reviewed shortlist; role = 'dropped' is skipped),
the SEBI taxonomies under data/raw/taxonomy/<version>/ and the parsed facts in the warehouse
(stg_facts / stg_filings / stg_units). A (taxonomy_version, concept) row is written only when the
concept is DEFINED in that version's schema AND USED in that version's filings - nothing is guessed.
Renamed predecessors (RENAMES below) are mapped to the successor's metric_id where the successor
does not exist yet. Each rename was checked against labels and values (docs/business_rules.md).

Outputs: dbt/seeds/concept_metric_map.csv and docs/metric_definitions.md.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion import config  # noqa: E402

SHORTLIST = config.DOCS_DIR / "metric_shortlist.csv"
SEED = config.DBT_DIR / "seeds" / "concept_metric_map.csv"
DOC = config.DOCS_DIR / "metric_definitions.md"
XSD = "{http://www.w3.org/2001/XMLSchema}"
XBRLI = "{http://www.xbrl.org/2003/instance}"

SEED_COLUMNS = [
    "taxonomy_version",
    "concept",
    "metric_id",
    "metric_name",
    "brsr_core_attribute",
    "role",
    "allowed_dimension_axes",
    "unit_raw_expected",
    "unit_std",
    "direction",
    "value_kind",
    "notes",
]

# concept -> (metric_id, plain-English name, unit_std). unit_std is the unit after normalisation.
METRICS: dict[str, tuple[str, str, str]] = {
    "Turnover": ("turnover_inr", "Turnover (revenue from operations)", "INR"),
    "TotalScope1Emissions": ("ghg_scope1_tco2e", "Scope 1 greenhouse gas emissions", "tCO2e"),
    "TotalScope2Emissions": ("ghg_scope2_tco2e", "Scope 2 greenhouse gas emissions", "tCO2e"),
    "TotalScope1AndScope2EmissionsIntensityPerRupeeOfTurnover": (
        "ghg_intensity_filed_tco2e_per_inr_cr",
        "Scope 1+2 emissions intensity as filed (per rupee crore of turnover)",
        "tCO2e/INR cr",
    ),
    "TotalScope3Emissions": ("ghg_scope3_tco2e", "Scope 3 greenhouse gas emissions", "tCO2e"),
    "TotalEnergyConsumedFromRenewableAndNonRenewableSources": (
        "energy_total_gj",
        "Total energy consumed (renewable + non-renewable)",
        "GJ",
    ),
    "TotalEnergyConsumedFromRenewableSources": (
        "energy_renewable_gj",
        "Energy consumed from renewable sources",
        "GJ",
    ),
    "EnergyIntensityPerRupeeOfTurnover": (
        "energy_intensity_filed_gj_per_inr_cr",
        "Energy intensity as filed (per rupee crore of turnover)",
        "GJ/INR cr",
    ),
    "TotalVolumeOfWaterWithdrawal": ("water_withdrawal_kl", "Total water withdrawal", "kl"),
    "TotalVolumeOfWaterConsumption": ("water_consumption_kl", "Total water consumption", "kl"),
    "WaterIntensityPerRupeeOfTurnover": (
        "water_intensity_filed_kl_per_inr_cr",
        "Water intensity as filed (per rupee crore of turnover)",
        "kl/INR cr",
    ),
    "TotalWasteGenerated": ("waste_generated_t", "Total waste generated", "t"),
    "TotalWasteRecovered": ("waste_recovered_t", "Total waste recovered", "t"),
    "TotalWasteDisposed": ("waste_disposed_t", "Total waste disposed", "t"),
    "LostTimeInjuryFrequencyRatePerOneMillionPersonHoursWorked": (
        "ltifr",
        "Lost time injury frequency rate (per million person-hours)",
        "per_million_hours",
    ),
    "TotalRecordableWorkRelatedInjuries": (
        "recordable_injuries_count",
        "Total recordable work-related injuries",
        "count",
    ),
    "NumberOfFatalities": ("fatalities_count", "Number of fatalities", "count"),
    "PercentageOfCostIncurredOnWellBeingMeasuresWithRespectToTotalRevenueOfTheCompany": (
        "wellbeing_cost_pct_revenue",
        "Spending on employee well-being as % of revenue",
        "pct",
    ),
    "NumberOfEmployeesOrWorkersIncludingDifferentlyAbled": (
        "headcount",
        "Number of employees and workers (incl. differently abled)",
        "count",
    ),
    "PercentageOfGrossWagesPaidToFemaleToTotalWagesPaid": (
        "female_wage_share_pct",
        "Share of gross wages paid to women",
        "pct",
    ),
    "PercentageOfComplaintsInRespectOfNumberOfEmployeesOrWorker": (
        "posh_complaints_pct_female",
        "POSH complaints as % of female employees/workers",
        "pct",
    ),
    "ComplaintsOnPOSHUpHeld": ("posh_complaints_upheld_count", "POSH complaints upheld", "count"),
    "PercentageOfFemaleBoardOfDirectors": (
        "female_board_pct",
        "Share of women on the board of directors",
        "pct",
    ),
    "TurnoverRate": ("attrition_rate_pct", "Employee/worker attrition (turnover) rate", "pct"),
    "PercentageOfDirectlySourcedFromMSMEsOrSmallProducers": (
        "msme_sourcing_pct",
        "Input material sourced directly from MSMEs / small producers",
        "pct",
    ),
    "PercentageOfJobCreation": (
        "job_creation_small_towns_pct",
        "Wages paid by location type (rural, semi-urban, urban, metro) as % of total",
        "pct",
    ),
    "NumberOfInstancesOfDataBreachesAlongWithImpact": (
        "data_breaches_count",
        "Number of data breaches",
        "count",
    ),
    "NumberOfDaysOfAccountsPayable": ("days_payable", "Days of accounts payable", "days"),
    "PercentageOfPurchasesFromRelatedPartiesInTotalPurchasesForShareOfRelatedPartyTransactions": (
        "rpt_purchases_pct",
        "Purchases from related parties as % of total purchases",
        "pct",
    ),
    "PercentageOfSalesToRelatedPartiesInTotalSalesForShareOfRelatedPartyTransactions": (
        "rpt_sales_pct",
        "Sales to related parties as % of total sales",
        "pct",
    ),
    "WhetherTheCompanyHasUndertakenAssessmentOrAssuranceOfTheBRSRCore": (
        "brsr_core_assurance_status",
        "Whether BRSR Core was assessed or assured",
        "",
    ),
    "TypeOfAssessmentOrAssuranceObtain": (
        "brsr_core_assurance_type",
        "Scope of the BRSR Core assessment/assurance (all or partial)",
        "",
    ),
    "ReportingBoundary": ("reporting_boundary", "Reporting boundary (standalone/consolidated)", ""),
    "NICCodeOfProductOrServiceSoldByTheEntity": (
        "nic_code",
        "NIC code of products/services (sector classification)",
        "",
    ),
}

# predecessor concept -> successor concept (same meaning, renamed between taxonomy versions)
RENAMES: dict[str, str] = {
    "TotalEnergyConsumption": "TotalEnergyConsumedFromRenewableAndNonRenewableSources",
    "TotalScope1AndScope2EmissionsPerRupeeOfTurnover": (
        "TotalScope1AndScope2EmissionsIntensityPerRupeeOfTurnover"
    ),
}

# Old taxonomies (2021-09-30, 2023-06-30) file quantities with unit 'pure'; the real unit is in a
# companion text fact (emissions only) or implied. See docs/business_rules.md.
OLD_PURE_NOTE = {
    "tCO2e": "unit 'pure' in this version - real unit in text fact UnitOf<concept>",
    "GJ": "unit 'pure' in this version - unit implied (bridged from the next filing)",
    "kl": "unit 'pure' in this version - unit implied (kl per BRSR format)",
    "t": "unit 'pure' in this version - unit implied (t per BRSR format)",
    "tCO2e/INR cr": "unit 'pure' in this version - unit in text fact; check only",
    "GJ/INR cr": "unit 'pure' in this version - unit implied; check only",
    "kl/INR cr": "unit 'pure' in this version - unit implied; check only",
}
ENUM_TYPES = {"ReportingOnTheBasis", "AssessmentOrAssurance", "AssuranceType"}


def read_shortlist() -> list[dict]:
    with SHORTLIST.open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["role"] != "dropped"]


def taxonomy_elements() -> dict[str, dict[str, str]]:
    """version -> {concept: local type name} from each version's core schema."""
    out: dict[str, dict[str, str]] = {}
    for vdir in sorted(p for p in config.TAXONOMY_DIR.iterdir() if p.is_dir()):
        xsd = next(vdir.rglob("core/in-capmkt.xsd"))
        root = etree.parse(str(xsd)).getroot()
        out[vdir.name] = {
            e.get("name"): (e.get("type") or "").split(":")[-1] for e in root.iter(XSD + "element")
        }
    return out


def facts_usage() -> dict[tuple[str, str], dict]:
    """(version, concept) -> {units, axes} from the warehouse staging models."""
    import duckdb

    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    rows = con.sql(
        """
        select f.taxonomy_version, x.concept,
               list(distinct coalesce(u.unit_label, '')) as units,
               list(distinct c.dimension_key) as keys
        from stg_facts x
        join stg_filings f using (filing_id)
        join stg_contexts c on c.filing_id = x.filing_id and c.context_id = x.context_ref
        left join stg_units u on u.filing_id = x.filing_id and u.unit_id = x.unit_ref
        group by all
        """
    ).fetchall()
    usage = {}
    for version, concept, units, keys in rows:
        axes = sorted({p.split("=")[0] for k in keys if k for p in k.split("|")})
        usage[(version, concept)] = {"units": sorted(u for u in units if u), "axes": axes}
    return usage


def value_kind(type_name: str, unit_std: str) -> str:
    if type_name == "durationItemType":
        return "duration"
    if type_name in ENUM_TYPES:
        return "enum"
    if type_name == "stringItemType":
        return "text"
    return "numeric" if unit_std else "text"


def build_rows(shortlist: list[dict], elements: dict, usage: dict) -> list[dict]:
    by_concept = {r["concept"]: r for r in shortlist}
    predecessors = defaultdict(list)
    for old, new in RENAMES.items():
        predecessors[new].append(old)

    rows = []
    for version, schema in elements.items():
        for concept, short in by_concept.items():
            metric_id, name, unit_std = METRICS[concept]
            candidates = [concept]
            if concept not in schema or (version, concept) not in usage:
                candidates += predecessors.get(concept, [])
            for filed in candidates:
                if filed not in schema or (version, filed) not in usage:
                    continue
                use = usage[(version, filed)]
                kind = value_kind(schema[filed], unit_std)
                notes = []
                if filed != concept:
                    notes.append(f"renamed predecessor of {concept}")
                if use["units"] == ["pure"] and unit_std in OLD_PURE_NOTE:
                    notes.append(OLD_PURE_NOTE[unit_std])
                if kind == "text" and unit_std:
                    notes.append("filed as text in this version - numbers parsed from text")
                if short["analytics_note"]:
                    notes.append(short["analytics_note"])
                rows.append(
                    {
                        "taxonomy_version": version,
                        "concept": filed,
                        "metric_id": metric_id,
                        "metric_name": name,
                        "brsr_core_attribute": short["brsr_core_attribute"],
                        "role": short["role"],
                        "allowed_dimension_axes": "|".join(use["axes"]),
                        "unit_raw_expected": "|".join(use["units"]),
                        "unit_std": unit_std,
                        "direction": short["direction"],
                        "value_kind": kind,
                        "notes": " | ".join(notes),
                    }
                )
                break  # successor found: do not also map the predecessor
    return sorted(rows, key=lambda r: (r["metric_id"], r["taxonomy_version"]))


def write_seed(rows: list[dict]) -> None:
    with SEED.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SEED_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def write_docs(rows: list[dict]) -> None:
    metrics: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        metrics[row["metric_id"]].append(row)
    order = {c: i for i, c in enumerate(METRICS)}
    lines = [
        "# Metric definitions",
        "",
        "Generated by `scripts/build_metric_catalogue.py` from `dbt/seeds/concept_metric_map.csv`"
        " - do not edit the table by hand (except the last column).",
        "",
        "Source concepts are the SEBI BRSR taxonomy concepts that feed the metric in each taxonomy"
        " version (renamed predecessors included). Units are after normalisation"
        " (`dbt/seeds/unit_normalisation.csv`, rules in [business_rules.md](business_rules.md)).",
        "",
        "| metric_id | Name | BRSR attribute | Role | unit_std | Direction | Source concepts per"
        " version | Breakdown axes | Notes | definition_in_my_words |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for metric_id, mrows in sorted(
        metrics.items(), key=lambda kv: order.get(_concept_of(kv[0]), 99)
    ):
        first = mrows[0]
        by_concept: dict[str, list[str]] = defaultdict(list)
        for r in mrows:
            by_concept[r["concept"]].append(r["taxonomy_version"])
        sources = "<br>".join(
            f"`{c}`: {', '.join(sorted(vs))}" for c, vs in sorted(by_concept.items())
        )
        notes = sorted({n for r in mrows for n in r["notes"].split(" | ") if n})
        lines.append(
            f"| `{metric_id}` | {_md(first['metric_name'])} | {_md(first['brsr_core_attribute'])}"
            f" | {first['role']} | {first['unit_std'] or '-'} | {first['direction']} | {sources}"
            f" | {_md(first['allowed_dimension_axes']) or '-'} | {_md('; '.join(notes))} | |"
        )
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _concept_of(metric_id: str) -> str:
    return next((c for c, m in METRICS.items() if m[0] == metric_id), "")


def read_seed() -> list[dict]:
    with SEED.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docs-only", action="store_true", help="regenerate docs from the seed")
    args = parser.parse_args()
    if args.docs_only:
        rows = read_seed()
    else:
        shortlist = read_shortlist()
        missing = [r["concept"] for r in shortlist if r["concept"] not in METRICS]
        if missing:
            raise SystemExit(f"shortlist concepts without a METRICS entry: {missing}")
        rows = build_rows(shortlist, taxonomy_elements(), facts_usage())
        write_seed(rows)
        print(f"{len(rows)} rows -> {config.display_path(SEED)}")
    write_docs(rows)
    print(f"-> {config.display_path(DOC)}")


if __name__ == "__main__":
    main()
