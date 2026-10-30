"""Generate the two Power BI projects (Week 12): powerbi/esg_lens_local and powerbi/esg_lens_public.

    python scripts/build_powerbi.py            # write the projects
    python scripts/build_powerbi.py --check    # fail if the committed projects are out of date

Format: Power BI Project (.pbip) with the semantic model in TMDL (Power BI Desktop 2.158).
Tables and column types come from the export queries of scripts/export_bi.py, read from the
warehouse with DESCRIBE, so the model always matches the Parquet files. Measures are defined
here once, mirror the semantic layer (docs/semantic_layer.md) and go into a `_Measures` table
with display folders and descriptions. Also written, for pasting into a blank report if the
project does not open: <project>.tmdl-script.tmdl (TMDL view) and <project>_measures.dax.

The public model reads only the rpt_public_* files and never recomputes a gated statistic from
company rows: group figures are read from rpt_public_group_metrics, where the 5-company rule is
already applied. No measure anywhere averages an intensity.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export_bi  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POWERBI = ROOT / "powerbi"
MARTS_YML = ROOT / "dbt" / "models" / "marts" / "_marts.yml"
CATALOGUE = ROOT / "dbt" / "seeds" / "kpi_catalogue.csv"
NAMESPACE = uuid.UUID("6b1d3c1e-58a5-4a63-9f1e-3f7c2a0e5d11")
COMPATIBILITY_LEVEL = 1600
PLACEHOLDER = "SET-ME: full path of the exports\\{audience} folder, no backslash at the end"

TYPES = {
    "VARCHAR": "string",
    "BOOLEAN": "boolean",
    "DATE": "dateTime",
    "TIMESTAMP": "dateTime",
    "DOUBLE": "double",
    "FLOAT": "double",
    "INTEGER": "int64",
    "BIGINT": "int64",
    "SMALLINT": "int64",
    "TINYINT": "int64",
    "HUGEINT": "int64",
}


def _tag(*parts: str) -> str:
    """A stable lineage tag, so that regenerating gives the same files."""
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def _quote(name: str) -> str:
    if name.replace("_", "").isalnum() and not name[0].isdigit():
        return name
    return "'" + name.replace("'", "''") + "'"


def _data_type(duckdb_type: str) -> str:
    base = duckdb_type.split("(")[0].upper()
    if base == "DECIMAL":
        return "double"
    if base not in TYPES:
        raise SystemExit(f"no Power BI type for DuckDB type {duckdb_type}")
    return TYPES[base]


# ------------------------------------------------------------------ the model as data


@dataclass
class Column:
    name: str
    data_type: str
    description: str = ""
    hidden: bool = False
    sort_by: str = ""


@dataclass
class Measure:
    name: str
    expression: str
    folder: str
    description: str
    format_string: str = ""


@dataclass
class Table:
    name: str
    columns: list[Column]
    source: str  # M expression
    description: str = ""
    measures: list[Measure] = field(default_factory=list)


@dataclass
class Model:
    audience: str  # local | public
    tables: list[Table]
    relationships: list[tuple[str, str]]  # ("table.column" many side, "table.column" one side)


def _column_docs() -> dict[str, dict[str, tuple[str, bool]]]:
    """Description and public_safe flag of every documented column of the gold models."""
    models = yaml.safe_load(MARTS_YML.read_text(encoding="utf-8"))["models"]
    docs: dict[str, dict[str, tuple[str, bool]]] = {}
    for model in models:
        docs[model["name"]] = {}
        for column in model.get("columns", []):
            meta = (column.get("config") or {}).get("meta") or column.get("meta") or {}
            safe = meta.get("public_safe", True)
            docs[model["name"]][column["name"]] = (
                " ".join(str(column.get("description", "")).split()),
                safe is not False,
            )
    return docs


def _parquet_source(path: str) -> str:
    return (
        "let\n"
        f'    Source = Parquet.Document(File.Contents(ExportFolder & "\\{path}"))\n'
        "in\n"
        "    Source"
    )


def _table(
    con: duckdb.DuckDBPyConnection,
    name: str,
    sql: str,
    path: str,
    docs: dict[str, tuple[str, bool]],
    description: str,
    hidden: tuple[str, ...] = (),
    local: bool = False,
) -> Table:
    columns = []
    for column, kind in export_bi.describe(con, export_bi.portable(con, sql)):
        text, safe = docs.get(column, ("", True))
        if local and not safe:
            text = "LOCAL ONLY - not public (publication policy). " + text
        columns.append(Column(column, _data_type(kind), text.strip(), column in hidden))
    return Table(name, columns, _parquet_source(path), description)


# ------------------------------------------------------------------ measures


def _ratio_of_sums(numerator: str, denominator: str, scale: int) -> str:
    body = (
        "VAR rows_with_both =\n"
        "    FILTER (\n"
        "        fct_company_year,\n"
        f"        NOT ISBLANK ( fct_company_year[{numerator}] )\n"
        f"            && fct_company_year[{denominator}] <> 0\n"
        "    )\n"
        "RETURN\n"
    )
    divide = (
        "DIVIDE (\n"
        f"        SUMX ( rows_with_both, fct_company_year[{numerator}] ),\n"
        f"        SUMX ( rows_with_both, fct_company_year[{denominator}] )\n"
        "    )"
    )
    return body + (f"    {scale} * " if scale != 1 else "    ") + divide


def _median(table: str, column: str) -> str:
    return (
        "MEDIANX (\n"
        f"    FILTER ( {table}, NOT ISBLANK ( {table}[{column}] ) ),\n"
        f"    {table}[{column}]\n"
        ")"
    )


def _companies_with(table: str, condition: str) -> str:
    return f"CALCULATE ( DISTINCTCOUNT ( {table}[isin] ), {condition} )"


RATIO_MEASURES = [
    # name, numerator, denominator, scale, format, semantic-layer metric, unit
    ("GHG intensity (whole group)", "ghg_s12_tco2e", "turnover_cr", 1, "#,##0.00",
     "ghg_intensity_agg", "tCO2e per Rs crore"),
    ("Energy intensity (whole group)", "energy_total_gj", "turnover_cr", 1, "#,##0.0",
     "energy_intensity_agg", "GJ per Rs crore"),
    ("Water intensity (whole group)", "water_consumption_kl", "turnover_cr", 1, "#,##0.0",
     "water_intensity_agg", "kl per Rs crore"),
    ("Waste intensity (whole group)", "waste_generated_t", "turnover_cr", 1, "#,##0.00",
     "waste_intensity_agg", "t per Rs crore"),
    ("Renewable share (whole group, %)", "energy_renewable_gj", "energy_total_gj", 100, "0.0",
     "renewable_share_agg", "%"),
    ("Women in workforce (whole group, %)", "headcount_female", "headcount_total", 100, "0.0",
     "female_workforce_agg", "%"),
]  # fmt: skip
MEDIAN_MEASURES = [
    ("GHG intensity (typical company)", "ghg_intensity_tco2e_per_cr", "#,##0.00",
     "ghg_intensity_median", "tCO2e per Rs crore"),
    ("Energy intensity (typical company)", "energy_intensity_gj_per_cr", "#,##0.0",
     "energy_intensity_median", "GJ per Rs crore"),
    ("Water intensity (typical company)", "water_intensity_kl_per_cr", "#,##0.0",
     "water_intensity_median", "kl per Rs crore"),
    ("Waste intensity (typical company)", "waste_intensity_t_per_cr", "#,##0.00",
     "waste_intensity_median", "t per Rs crore"),
]  # fmt: skip
COVERAGE = [
    ("Companies with GHG intensity", "ghg_intensity_tco2e_per_cr"),
    ("Companies with energy intensity", "energy_intensity_gj_per_cr"),
    ("Companies with water intensity", "water_intensity_kl_per_cr"),
    ("Companies with waste intensity", "waste_intensity_t_per_cr"),
    ("Companies with renewable share", "renewable_share_pct"),
    ("Companies with women in workforce", "female_workforce_pct"),
]
FOLDERS = {
    "coverage": "1 Coverage",
    "intensity": "2 Intensity and shares (group)",
    "dqs": "3 Disclosure quality (group)",
    "restatement": "4 Restatements (group)",
    "status": "5 Data status and labels",
    "concentration": "6 Concentration (local only)",
    "company": "7 Company card",
}
MIN_5 = (
    " Shown publicly only for 5 companies or more: check the matching 'Companies with ...' measure."
)


def local_measures() -> list[Measure]:
    m: list[Measure] = [
        Measure(
            "Companies in selection",
            "DISTINCTCOUNT ( fct_company_year[isin] )",
            FOLDERS["coverage"],
            "Companies with a report in the current selection (semantic layer: companies_reporting).",
            "0",
        )
    ]
    for name, column in COVERAGE:
        m.append(
            Measure(
                name,
                _companies_with("fct_company_year", f"NOT ISBLANK ( fct_company_year[{column}] )"),
                FOLDERS["coverage"],
                f"Companies with a value for {column}: the count that decides whether a group "
                "figure built on it may be shown publicly (5 or more).",
                "0",
            )
        )
    for name, numerator, denominator, scale, fmt, metric, unit in RATIO_MEASURES:
        m.append(
            Measure(
                name,
                _ratio_of_sums(numerator, denominator, scale),
                FOLDERS["intensity"],
                f"{unit}. Whole group: sum of {numerator} over sum of {denominator}, over the "
                f"companies that have both (semantic layer: {metric}). Large companies weigh "
                "more. Never an average of company ratios." + MIN_5,
                fmt,
            )
        )
    for name, column, fmt, metric, unit in MEDIAN_MEASURES:
        m.append(
            Measure(
                name,
                _median("fct_company_year", column),
                FOLDERS["intensity"],
                f"{unit}. Typical company: the median of {column} over the company-years in the "
                f"selection (semantic layer: {metric}). Every company weighs the same; use it "
                "within one year." + MIN_5,
                fmt,
            )
        )
    m.append(
        Measure(
            "Scope 3 disclosed (% of reports)",
            "100\n    * DIVIDE (\n"
            "        COUNTROWS ( FILTER ( fct_company_year, fct_company_year[scope3_disclosed] = TRUE () ) ),\n"
            "        COUNTROWS ( fct_company_year )\n"
            "    )",
            FOLDERS["intensity"],
            "Company reports with a Scope 3 figure out of all reports, in % (semantic layer: "
            "scope3_disclosed_share)." + MIN_5,
            "0.0",
        )
    )
    dq = "fct_disclosure_quality"
    m += [
        Measure(
            "DQS average",
            f"AVERAGE ( {dq}[dqs_total] )",
            FOLDERS["dqs"],
            "Average Disclosure Quality Score (semantic layer: dqs_avg). A score, not an "
            "intensity, so an average is allowed. Compare within one financial year only." + MIN_5,
            "0.0",
        ),
        Measure(
            "DQS median",
            _median(dq, "dqs_total"),
            FOLDERS["dqs"],
            "Median Disclosure Quality Score (semantic layer: dqs_median). Compare within one "
            "financial year only." + MIN_5,
            "0.0",
        ),
        Measure(
            "Grade A share (%)",
            "100\n    * DIVIDE (\n"
            f'        COUNTROWS ( FILTER ( {dq}, {dq}[dqs_grade] = "A" ) ),\n'
            "        COUNTROWS (\n"
            f"            FILTER ( {dq}, NOT ISBLANK ( {dq}[dqs_grade] ) && {dq}[dqs_grade] "
            '<> "insufficient_data" )\n'
            "        )\n"
            "    )",
            FOLDERS["dqs"],
            "Graded company-years with grade A, in % (semantic layer: dqs_grade_a_share)." + MIN_5,
            "0.0",
        ),
        Measure(
            "Voluntary depth average",
            f"AVERAGE ( {dq}[dqs_voluntary_depth] )",
            FOLDERS["dqs"],
            "Average share (0-1) of Leadership indicators answered (semantic layer: "
            "voluntary_depth_avg)." + MIN_5,
            "0.00",
        ),
        Measure(
            "Companies with DQS",
            _companies_with(dq, f"NOT ISBLANK ( {dq}[dqs_total] )"),
            FOLDERS["coverage"],
            "Companies with a Disclosure Quality Score (semantic layer: companies_with_dqs).",
            "0",
        ),
        Measure(
            "Companies with DQS grade",
            _companies_with(dq, f'{dq}[dqs_grade] IN {{ "A", "B", "C", "D" }}'),
            FOLDERS["coverage"],
            "Companies with a grade A to D (semantic layer: companies_with_dqs_grade).",
            "0",
        ),
    ]
    rs = "fct_restatement"
    m += [
        Measure(
            "Material restatements",
            f'COUNTROWS ( FILTER ( {rs}, {rs}[classification] = "material" ) )',
            FOLDERS["restatement"],
            "Figures changed materially in the next year's report (semantic layer: "
            "material_restatements). Follows the year of the restated value. A restatement is "
            "not wrongdoing.",
            "#,##0",
        ),
        Measure(
            "Material restatement share (%)",
            "100\n    * DIVIDE (\n"
            "        [Material restatements],\n"
            f"        COUNTROWS ( FILTER ( {rs}, {rs}[is_compared] = TRUE () ) )\n"
            "    )",
            FOLDERS["restatement"],
            "Compared figures restated materially, in % (semantic layer: "
            "material_restatement_share). Empty for the latest year: no later report yet." + MIN_5,
            "0.0",
        ),
        Measure(
            "Suspected scale errors",
            f'COUNTROWS ( FILTER ( {rs}, {rs}[classification] = "suspected_scale_error" ) )',
            FOLDERS["restatement"],
            "Figures more than 100 times apart between two reports: unit slips, not "
            "restatements (semantic layer: suspected_scale_errors).",
            "#,##0",
        ),
        Measure(
            "Companies with compared restatements",
            _companies_with(rs, f"{rs}[is_compared] = TRUE ()"),
            FOLDERS["coverage"],
            "Companies with at least one figure compared with the next report (semantic "
            "layer: companies_with_compared_restatements).",
            "0",
        ),
    ]
    m += [
        Measure(
            "Year status",
            "VAR selected_year = MAX ( dim_fiscal_year[fy_sort] )\n"
            "VAR latest_year = CALCULATE ( MAX ( dim_fiscal_year[fy_sort] ), ALL ( dim_fiscal_year ) )\n"
            "RETURN\n"
            "    IF (\n"
            "        NOT ISBLANK ( selected_year ),\n"
            '        IF ( selected_year = latest_year, "Provisional: no later report yet", "Final" )\n'
            "    )",
            FOLDERS["status"],
            "Label for titles and tooltips: the latest year is provisional (its figures and "
            "scores can still change when the next reports arrive).",
        ),
        Measure(
            "Public rule label",
            'IF ( [Companies in selection] < 5, "n<5: would not be shown publicly", "" )',
            FOLDERS["status"],
            "Text for a card or tooltip: a group of fewer than 5 companies gets no published "
            "statistic.",
        ),
        Measure(
            "Confidence of YoY change",
            "SELECTEDVALUE ( q03_yoy_changes_with_confidence[confidence] )",
            FOLDERS["status"],
            "Week 10 confidence label of a year-on-year GHG intensity change: confirmed, "
            "provisional, inferred_unit, restated_later, one_year_reversal or not_confirmed. "
            "Only confirmed changes are ranked.",
        ),
    ]
    fy = "fct_company_year"
    m += [
        Measure(
            "Scope 1+2 emissions (local only)",
            f"SUM ( {fy}[ghg_s12_tco2e] )",
            FOLDERS["concentration"],
            "LOCAL ONLY: a total of filed values (tCO2e). Never show it in anything published; "
            "publish the shares below instead.",
            "#,##0",
        ),
        Measure(
            "Share of selected emissions (%)",
            "100\n    * DIVIDE (\n"
            "        [Scope 1+2 emissions (local only)],\n"
            "        CALCULATE ( [Scope 1+2 emissions (local only)], ALLSELECTED ( dim_company ) )\n"
            "    )",
            FOLDERS["concentration"],
            "A company's share of the Scope 1+2 emissions of all selected companies, in %.",
            "0.0",
        ),
        Measure(
            "Cumulative share of emissions (%)",
            "VAR current_emissions = [Scope 1+2 emissions (local only)]\n"
            "VAR companies =\n"
            "    ADDCOLUMNS (\n"
            "        ALLSELECTED ( dim_company[display_name] ),\n"
            '        "@emissions", [Scope 1+2 emissions (local only)]\n'
            "    )\n"
            "RETURN\n"
            "    IF (\n"
            "        NOT ISBLANK ( current_emissions ),\n"
            "        100\n"
            "            * DIVIDE (\n"
            "                SUMX ( FILTER ( companies, [@emissions] >= current_emissions ), [@emissions] ),\n"
            "                SUMX ( companies, [@emissions] )\n"
            "            )\n"
            "    )",
            FOLDERS["concentration"],
            "Pareto line: share of emissions held by this company and every larger emitter in "
            "the selection, in %. Use one year at a time.",
            "0.0",
        ),
        Measure(
            "Emitter rank",
            "IF (\n"
            "    NOT ISBLANK ( [Scope 1+2 emissions (local only)] ),\n"
            "    RANKX ( ALLSELECTED ( dim_company[display_name] ), [Scope 1+2 emissions (local only)], , DESC, DENSE )\n"
            ")",
            FOLDERS["concentration"],
            "1 = largest emitter in the selection.",
            "0",
        ),
    ]
    pc, pb = "fct_company_kpi_percentile", "fct_peer_benchmark"
    m += [
        Measure(
            "Company value (local only)",
            f"SELECTEDVALUE ( {pc}[value] )",
            FOLDERS["company"],
            "LOCAL ONLY for filed KPIs: the company's own value of the KPI on the row. Computed "
            "intensities are public; filed percentages are not.",
            "#,##0.00",
        ),
        Measure(
            "Peer percentile",
            f"SELECTEDVALUE ( {pc}[percentile_in_group] )",
            FOLDERS["company"],
            "0-100, 100 = best in the ranking group and year. Empty when the group has fewer "
            "than 5 companies with a value or the KPI is not material there (see 'Not ranked "
            "because').",
            "0.0",
        ),
        Measure(
            "Not ranked because",
            f"SELECTEDVALUE ( {pc}[percentile_null_reason] )",
            FOLDERS["company"],
            "Why there is no percentile: no_value, not_material, group_n_lt_5, flagged_value, "
            "no_direction.",
        ),
        Measure(
            "Peer median (ranking group)",
            f"VAR kpi = SELECTEDVALUE ( {pc}[kpi_name] )\n"
            f"VAR ranking_group = SELECTEDVALUE ( {pc}[ranking_group] )\n"
            "RETURN\n"
            "    CALCULATE (\n"
            f"        MAX ( {pb}[median_value] ),\n"
            f"        {pb}[kpi_name] = kpi,\n"
            f"        {pb}[ranking_group] = ranking_group,\n"
            f"        {pb}[has_min_n] = TRUE ()\n"
            "    )",
            FOLDERS["company"],
            "Median of the company's ranking group for the KPI on the row and the selected "
            "year (fct_peer_benchmark, only with 5 or more companies). MAX picks the one "
            "matching row.",
            "#,##0.00",
        ),
        Measure(
            "Company DQS",
            f"SELECTEDVALUE ( {dq}[dqs_total] )",
            FOLDERS["company"],
            "The selected company's Disclosure Quality Score in the selected year.",
            "0.0",
        ),
        Measure(
            "Company DQS percentile",
            f"SELECTEDVALUE ( {dq}[dqs_percentile_in_group] )",
            FOLDERS["company"],
            "Percentile of the score within the ranking group and year (100 = best).",
            "0.0",
        ),
        Measure(
            "Company DQS status",
            f'IF ( SELECTEDVALUE ( {dq}[is_provisional] ), "Provisional", "Final" )',
            FOLDERS["company"],
            "Provisional = the temporal check could not be run yet: the score can still fall.",
        ),
    ]
    return m


def _catalogue() -> list[dict[str, str]]:
    with CATALOGUE.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def public_measures(group_columns: list[str], provisional_year: str) -> list[Measure]:
    g = "rpt_public_group_metrics"
    by_name = {row["kpi_name"]: row for row in _catalogue()}
    m: list[Measure] = [
        Measure(
            "Companies in selection",
            "DISTINCTCOUNT ( rpt_public_company_year[isin] )",
            FOLDERS["coverage"],
            "Companies with a report in the current selection.",
            "0",
        ),
        Measure(
            "Group rows in selection",
            f"COUNTROWS ( {g} )",
            FOLDERS["status"],
            "The group figures show a value only when exactly one row of "
            "rpt_public_group_metrics is selected: one group type, one group, one year.",
            "0",
        ),
        Measure(
            "Withheld note",
            f"VAR reason = IF ( COUNTROWS ( {g} ) = 1, MAX ( {g}[suppressed_reason] ) )\n"
            "RETURN\n"
            "    SWITCH (\n"
            "        TRUE (),\n"
            "        ISBLANK ( reason ), BLANK (),\n"
            '        CONTAINSSTRING ( reason, "fewer_than_5" ) && CONTAINSSTRING ( reason, "not_yet" ),\n'
            '            "n<5; restatements not yet observable",\n'
            '        CONTAINSSTRING ( reason, "fewer_than_5" ), "n<5: fewer than 5 companies",\n'
            '        "Restatements not yet observable: no later report"\n'
            "    )",
            FOLDERS["status"],
            "Why a group figure is empty: fewer than 5 companies (n<5), or a restatement figure "
            "of a year with no later report.",
        ),
        Measure(
            "Year status",
            "VAR y = SELECTEDVALUE ( dim_fiscal_year[fiscal_year_label] )\n"
            "RETURN\n"
            "    SWITCH (\n"
            "        TRUE (),\n"
            "        ISBLANK ( y ), BLANK (),\n"
            f'        y = "{provisional_year}", "Provisional year",\n'
            '        "Confirmed year"\n'
            "    )",
            FOLDERS["status"],
            f"Provisional year = {provisional_year}, the latest year: no later report has "
            "confirmed its figures yet. Blank unless one year is selected.",
        ),
    ]
    for column in group_columns:
        row = by_name.get(column)
        if row is None:
            continue
        is_count = row["metric_type"] in ("count", "count_distinct")
        folder = (
            FOLDERS["coverage"]
            if is_count
            else {
                "fct_disclosure_quality": FOLDERS["dqs"],
                "fct_restatement": FOLDERS["restatement"],
            }.get(row["source_model"], FOLDERS["intensity"])
        )
        unit = row["unit"]
        fmt = "0" if is_count else ("0.0" if unit in ("%", "points (0-100)") else "#,##0.00")
        rule = "" if is_count else " Blank when withheld: see 'Withheld note'."
        m.append(
            Measure(
                row["label"],
                f"IF ( COUNTROWS ( {g} ) = 1, MAX ( {g}[{column}] ) )",
                folder,
                f"{unit}. {row['definition_plain']} Published value from {g}.{column}; shown "
                f"only when one group, one group type and one year are selected.{rule}",
                fmt,
            )
        )
    cy, dq = "rpt_public_company_year", "rpt_public_disclosure_quality"
    for name, column, fmt in (
        ("Company: GHG intensity", "ghg_intensity_tco2e_per_cr", "#,##0.00"),
        ("Company: energy intensity", "energy_intensity_gj_per_cr", "#,##0.0"),
        ("Company: water intensity", "water_intensity_kl_per_cr", "#,##0.0"),
        ("Company: waste intensity", "waste_intensity_t_per_cr", "#,##0.00"),
        ("Company: renewable share (%)", "renewable_share_pct", "0.0"),
        ("Company: women in workforce (%)", "female_workforce_pct", "0.0"),
        ("Company: pay-equity gap (pp)", "pay_equity_gap_pp", "+0.0;-0.0;0.0"),
    ):
        m.append(
            Measure(
                name,
                f"SELECTEDVALUE ( {cy}[{column}] )",
                FOLDERS["company"],
                f"The selected company's {column} in the selected year (computed by ESG Lens "
                "India; public).",
                fmt,
            )
        )
    for name, column, fmt in (
        ("Company: DQS", "dqs_total", "0.0"),
        ("Company: DQS grade", "dqs_grade", ""),
        ("Company: DQS rank in group", "dqs_rank_in_group", "0"),
        ("Company: DQS percentile in group", "dqs_percentile_in_group", "0.0"),
    ):
        m.append(
            Measure(
                name,
                f"SELECTEDVALUE ( {dq}[{column}] )",
                FOLDERS["company"],
                f"The selected company's {column} in the selected year.",
                fmt,
            )
        )
    m.append(
        Measure(
            "Company: data status",
            f'IF ( SELECTEDVALUE ( {dq}[is_provisional] ), "Provisional", "Final" )',
            FOLDERS["company"],
            "Provisional = the latest year: no later report has confirmed the figures yet.",
        )
    )
    # --- concentration (shares and ranks of rpt_public_concentration; never tonnes)
    cc = "rpt_public_concentration"
    concentration = FOLDERS["concentration"].replace(" (local only)", " (shares)")
    for name, column, fmt, text in (
        (
            "Emitter rank",
            "emitter_rank",
            "0",
            "1 = largest Scope 1+2 emitter of the year among all companies covered.",
        ),
        (
            "Share of total emissions (%)",
            "share_of_total_pct",
            "0.0",
            "The company's share of the Scope 1+2 emissions of all companies covered that year, in %. Use with dim_company[display_name] on the axis and one year selected.",
        ),
        (
            "Cumulative share of emissions (%)",
            "cumulative_share_pct",
            "0.0",
            "Share held by this company and every larger emitter together, in %: the Pareto line.",
        ),
    ):
        m.append(Measure(name, f"SELECTEDVALUE ( {cc}[{column}] )", concentration, text, fmt))
    for top in (5, 10):
        m.append(
            Measure(
                f"Top-{top} share of emissions (%)",
                "CALCULATE (\n"
                f"    SELECTEDVALUE ( {cc}[cumulative_share_pct] ),\n"
                f"    {cc}[emitter_rank] = {top},\n"
                "    REMOVEFILTERS ( dim_company )\n"
                ")",
                concentration,
                f"Share of the year's Scope 1+2 emissions held by the {top} largest emitters, in %. "
                "Select one year; company and group slicers are ignored on purpose (the share is of "
                "all companies covered).",
                "0.0",
            )
        )
    m.append(
        Measure(
            "Companies for 80% of emissions",
            "VAR below_80 =\n"
            "    CALCULATE (\n"
            f"        COUNTROWS ( {cc} ),\n"
            f"        {cc}[cumulative_share_pct] < 80,\n"
            "        REMOVEFILTERS ( dim_company )\n"
            "    )\n"
            "RETURN\n"
            "    IF ( HASONEVALUE ( dim_fiscal_year[fiscal_year_label] ), below_80 + 1 )",
            concentration,
            "How many of the largest emitters it takes to reach 80% of the year's Scope 1+2 "
            "emissions. Select one year.",
            "0",
        )
    )
    # --- positions in the ranking group (rpt_public_company_percentile)
    pc = "rpt_public_company_percentile"
    for name, column, fmt, text in (
        (
            "Company: peer percentile",
            "percentile_in_group",
            "0.0",
            "Percentile in the ranking group for the KPI on the row (100 = best). Put kpi_label on the rows of a table and select one company and year.",
        ),
        (
            "Company: rank in group",
            "rank_in_group",
            "0",
            "Rank in the ranking group for the KPI on the row (1 = best).",
        ),
        (
            "Company: companies in group",
            "n_in_group",
            "0",
            "Companies of the ranking group with a value of the KPI: the base of the rank. Below 5 there is no rank.",
        ),
        (
            "Company: KPI value (public KPIs)",
            "kpi_value_public",
            "#,##0.00",
            "The company's value of the KPI on the row, only for KPIs we compute (empty for filed values).",
        ),
    ):
        m.append(Measure(name, f"SELECTEDVALUE ( {pc}[{column}] )", FOLDERS["company"], text, fmt))
    m.append(
        Measure(
            "Company: ranking status",
            f"VAR ranked = SELECTEDVALUE ( {pc}[is_ranked] )\n"
            f"VAR reason = SELECTEDVALUE ( {pc}[reason_not_ranked] )\n"
            "RETURN\n"
            "    SWITCH (\n"
            "        TRUE (),\n"
            '        ranked = TRUE (), "ranked",\n'
            '        reason = "not_material", "not ranked for this group (not material)",\n'
            '        reason = "group_n_lt_5", "not ranked: fewer than 5 companies (n<5)",\n'
            '        reason = "flagged_value", "not ranked: value flagged",\n'
            '        reason = "no_direction", "not ranked: no better or worse direction",\n'
            "        BLANK ()\n"
            "    )",
            FOLDERS["company"],
            "Why the KPI on the row has a rank or not. A KPI that is not material for the ranking "
            "group is not ranked, although its group median is still shown as a description.",
        )
    )
    # --- item: "not ranked for this group" next to a ranking group's median
    for label, kpi in (
        ("GHG intensity", "ghg_intensity_tco2e_per_cr"),
        ("energy intensity", "energy_intensity_gj_per_cr"),
        ("water intensity", "water_intensity_kl_per_cr"),
        ("waste intensity", "waste_intensity_t_per_cr"),
    ):
        m.append(
            Measure(
                f"Ranking note: {label}",
                f"VAR group_type = SELECTEDVALUE ( {g}[group_type] )\n"
                f"VAR ranking_group = SELECTEDVALUE ( {g}[group_value] )\n"
                f"VAR fiscal_year = SELECTEDVALUE ( {g}[fiscal_year_label] )\n"
                "VAR not_material =\n"
                "    CALCULATE (\n"
                f"        COUNTROWS ( {pc} ),\n"
                f"        REMOVEFILTERS ( {pc} ),\n"
                f"        {pc}[ranking_group] = ranking_group,\n"
                f"        {pc}[fiscal_year_label] = fiscal_year,\n"
                f'        {pc}[kpi_name] = "{kpi}",\n'
                f'        {pc}[reason_not_ranked] = "not_material"\n'
                "    )\n"
                "RETURN\n"
                '    IF ( group_type = "ranking_group" && not_material > 0, "not ranked for this group (not material)" )',
                FOLDERS["intensity"],
                f"Label for a ranking group's {label} median: companies are not ranked on it in "
                "this group because the KPI is not material there (for example GHG intensity for "
                "Financials). The median is still shown, as a description of the group.",
            )
        )
    for name, column in (
        ("Peer median: GHG intensity", "ghg_intensity_median"),
        ("Peer median: DQS", "dqs_median"),
    ):
        m.append(
            Measure(
                name,
                f"VAR ranking_group = SELECTEDVALUE ( {cy}[ranking_group] )\n"
                f"VAR fiscal_year = SELECTEDVALUE ( {cy}[fiscal_year_label] )\n"
                "RETURN\n"
                "    CALCULATE (\n"
                f"        MAX ( {g}[{column}] ),\n"
                f"        REMOVEFILTERS ( {g} ),\n"
                f'        {g}[group_type] = "ranking_group",\n'
                f"        {g}[group_value] = ranking_group,\n"
                f"        {g}[fiscal_year_label] = fiscal_year\n"
                "    )",
                FOLDERS["company"],
                f"The published {column} of the selected company's ranking group and year "
                "(blank when withheld, n<5). MAX picks the one matching row.",
                "0.0" if column == "dqs_median" else "#,##0.00",
            )
        )
    return m


# ------------------------------------------------------------------ the two models


def local_model(con: duckdb.DuckDBPyConnection) -> Model:
    docs = _column_docs()
    queries = export_bi.analysis_queries()
    keys = ("isin", "fiscal_year_label", "value_fiscal_year_label")
    tables = []
    for name, sql in export_bi.LOCAL_TABLES.items():
        hidden = keys if name.startswith("fct_") else ()
        tables.append(
            _table(con, name, sql, f"{name}.parquet", docs.get(name, {}), "", hidden, local=True)
        )
    for result_id in export_bi.ANALYSIS_IN_MODEL:
        file, result = result_id.split("__")
        name = f"{file[:3]}_{result}"
        tables.append(
            _table(
                con,
                name,
                queries[result_id],
                f"analysis\\{result_id}.parquet",
                {},
                f"Week 10 result {result_id} (analysis/sql/{file}.sql). Local only.",
                local=True,
            )
        )
    for table in tables:
        if table.name == "dim_fiscal_year":
            for column in table.columns:
                if column.name == "fiscal_year_label":
                    column.sort_by = "fy_sort"
    tables.append(_measures_table(local_measures()))
    relationships = [
        ("fct_company_year.isin", "dim_company.isin"),
        ("fct_company_year.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("fct_disclosure_quality.isin", "dim_company.isin"),
        ("fct_disclosure_quality.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("fct_restatement.isin", "dim_company.isin"),
        ("fct_restatement.value_fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("fct_restatement.metric_id", "dim_metric.metric_id"),
        ("fct_company_kpi_percentile.isin", "dim_company.isin"),
        ("fct_company_kpi_percentile.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("fct_peer_benchmark.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("q01_ghg_intensity_by_sector.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("q02_concentration_by_year.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("q02_pareto_top10_by_year.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
    ]
    return Model("local", tables, relationships)


def public_model(con: duckdb.DuckDBPyConnection) -> Model:
    docs = _column_docs()
    tables = [
        _table(
            con,
            name,
            sql,
            f"{name}.parquet",
            docs.get(name, {}),
            f"Public model {name}: derived values only (docs/publication_policy.md).",
            ("isin",) if name != "rpt_public_restatement_summary" else (),
        )
        for name, sql in export_bi.PUBLIC_TABLES.items()
    ]
    tables.append(
        Table(
            "dim_company",
            [
                Column(name, "string")
                for name in (
                    "isin",
                    "display_name",
                    "symbol",
                    "peer_group",
                    "sector_group",
                    "ranking_group",
                    "ownership_type",
                    "business_group",
                )
            ],  # fmt: skip
            "let\n"
            "    Source = rpt_public_company_year,\n"
            '    Latest = Table.Buffer ( Table.Sort ( Source, {{"fiscal_year_label", Order.Descending}} ) ),\n'
            '    Kept = Table.SelectColumns ( Latest, {"isin", "display_name", "symbol", "peer_group", '
            '"sector_group", "ranking_group", "ownership_type", "business_group"} ),\n'
            '    Companies = Table.Distinct ( Kept, {"isin"} )\n'
            "in\n"
            "    Companies",
            "One row per company (its latest name and groups), built from rpt_public_company_year.",
        )
    )
    tables.append(
        Table(
            "dim_fiscal_year",
            [Column("fiscal_year_label", "string", sort_by="fy_start_year"),
             Column("fy_start_year", "int64", "Calendar year in which the financial year starts.")],
            "let\n"
            "    Years = Table.Distinct (\n"
            "        Table.Combine ( {\n"
            '            Table.SelectColumns ( rpt_public_company_year, {"fiscal_year_label"} ),\n'
            '            Table.SelectColumns ( rpt_public_disclosure_quality, {"fiscal_year_label"} ),\n'
            '            Table.SelectColumns ( rpt_public_group_metrics, {"fiscal_year_label"} )\n'
            "        } )\n"
            "    ),\n"
            "    WithStart = Table.AddColumn ( Years, \"fy_start_year\", "
            "each Number.FromText ( Text.Middle ( [fiscal_year_label], 2, 4 ) ), Int64.Type )\n"
            "in\n"
            "    WithStart",
            "Financial years of the public tables, sorted by start year.",
        )
    )  # fmt: skip
    group_columns = [
        c.name for c in next(t for t in tables if t.name == "rpt_public_group_metrics").columns
    ]
    (latest_year,) = con.sql(
        "select max(fiscal_year_label) from rpt_public_company_year"
    ).fetchone()
    tables.append(_measures_table(public_measures(group_columns, latest_year)))
    relationships = [
        ("rpt_public_company_year.isin", "dim_company.isin"),
        ("rpt_public_company_year.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("rpt_public_disclosure_quality.isin", "dim_company.isin"),
        ("rpt_public_disclosure_quality.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("rpt_public_group_metrics.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("rpt_public_concentration.isin", "dim_company.isin"),
        ("rpt_public_concentration.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("rpt_public_company_percentile.isin", "dim_company.isin"),
        ("rpt_public_company_percentile.fiscal_year_label", "dim_fiscal_year.fiscal_year_label"),
        ("rpt_public_ghg_yoy.isin", "dim_company.isin"),
    ]
    return Model("public", tables, relationships)


def _measures_table(measures: list[Measure]) -> Table:
    return Table(
        "_Measures",
        [Column("Placeholder", "string", "Keeps the measure table loadable.", hidden=True)],
        "let\n    Source = #table ( type table [Placeholder = text], {} )\nin\n    Source",
        "All measures, in display folders. Group figures mirror the semantic layer.",
        measures,
    )


# ------------------------------------------------------------------ TMDL


def _description(text: str, indent: str) -> list[str]:
    return [f"{indent}/// {line}" for line in text.splitlines() if line.strip()] if text else []


def _expression(text: str, indent: str) -> list[str]:
    return [f"{indent}{line}" if line else "" for line in text.splitlines()]


def table_tmdl(table: Table) -> str:
    out = _description(table.description, "")
    out.append(f"table {_quote(table.name)}")
    out.append(f"\tlineageTag: {_tag('table', table.name)}")
    out.append("")
    for measure in table.measures:
        out += _description(measure.description, "\t")
        out.append(f"\tmeasure {_quote(measure.name)} =")
        out += _expression(measure.expression, "\t\t\t")
        if measure.format_string:
            out.append(f"\t\tformatString: {measure.format_string}")
        out.append(f"\t\tdisplayFolder: {measure.folder}")
        out.append(f"\t\tlineageTag: {_tag('measure', table.name, measure.name)}")
        out.append("")
    for column in table.columns:
        out += _description(column.description, "\t")
        out.append(f"\tcolumn {_quote(column.name)}")
        out.append(f"\t\tdataType: {column.data_type}")
        if column.hidden:
            out.append("\t\tisHidden")
        out.append(f"\t\tlineageTag: {_tag('column', table.name, column.name)}")
        out.append("\t\tsummarizeBy: none")
        out.append(f"\t\tsourceColumn: {column.name}")
        if column.sort_by:
            out.append(f"\t\tsortByColumn: {column.sort_by}")
        out.append("")
    out.append(f"\tpartition {_quote(table.name)} = m")
    out.append("\t\tmode: import")
    out.append("\t\tsource =")
    out += _expression(table.source, "\t\t\t\t")
    out.append("")
    return "\n".join(out) + "\n"


def _expressions_tmdl(audience: str) -> str:
    value = PLACEHOLDER.format(audience=audience)
    return (
        f"/// Folder that holds the exported Parquet files (exports\\{audience}). Set it once in\n"
        "/// Power BI Desktop: Transform data > Edit parameters. Do not commit your own path.\n"
        f'expression ExportFolder = "{value}" meta [IsParameterQuery = true, Type = "Text", '
        "IsParameterQueryRequired = true]\n"
        f"\tlineageTag: {_tag('expression', audience, 'ExportFolder')}\n\n"
        "\tannotation PBI_ResultType = Text\n"
    )


def _relationships_tmdl(model: Model) -> str:
    out = []
    for many, one in model.relationships:
        out.append(f"relationship {_tag('relationship', model.audience, many, one)}")
        out.append(f"\tfromColumn: {many}")
        out.append(f"\ttoColumn: {one}")
        out.append("")
    return "\n".join(out)


SCHEMA_ROOT = "https://developer.microsoft.com/json-schemas/fabric/item/report"
PAGE_ID = "overview"  # PBIR page folder / name: letters, digits, _ and - only
# Report pages in order: (folder / name, display name). The public report carries the
# five-page build of docs/powerbi_build_guide.md; the local one keeps the Overview only.
PAGES = {
    "public": (("overview", "Overview"), ("decarbonisation", "Decarbonisation")),
    "local": (("overview", "Overview"),),
}


def project_files(model: Model) -> dict[str, str]:
    """Relative path -> file content of one Power BI project."""
    name = f"esg_lens_{model.audience}"
    model_dir = f"{name}.SemanticModel"
    report_dir = f"{name}.Report"
    files = {
        f"{name}.pbip": json.dumps(
            {
                "version": "1.0",
                "artifacts": [{"report": {"path": report_dir}}],
                "settings": {"enableAutoRecovery": True},
            },
            indent=2,
        ),
        f"{report_dir}/definition.pbir": json.dumps(
            {
                "$schema": f"{SCHEMA_ROOT}/definitionProperties/2.0.0/schema.json",
                "version": "4.0",
                "datasetReference": {"byPath": {"path": f"../{model_dir}"}},
            },
            indent=2,
        ),
        f"{report_dir}/definition/version.json": json.dumps(
            {
                "$schema": f"{SCHEMA_ROOT}/definition/versionMetadata/1.0.0/schema.json",
                "version": "2.0.0",
            },
            indent=2,
        ),
        f"{report_dir}/definition/report.json": json.dumps(
            {
                "$schema": f"{SCHEMA_ROOT}/definition/report/3.2.0/schema.json",
                "themeCollection": {
                    "baseTheme": {
                        "name": "CY24SU10",
                        "reportVersionAtImport": {
                            "visual": "1.8.50",
                            "report": "2.0.50",
                            "page": "1.3.50",
                        },
                        "type": "SharedResources",
                    }
                },
            },
            indent=2,
        ),
        f"{report_dir}/definition/pages/pages.json": json.dumps(
            {
                "$schema": f"{SCHEMA_ROOT}/definition/pagesMetadata/1.0.0/schema.json",
                "pageOrder": [page for page, _ in PAGES[model.audience]],
                "activePageName": PAGE_ID,
            },
            indent=2,
        ),
        **{
            f"{report_dir}/definition/pages/{page}/page.json": json.dumps(
                {
                    "$schema": f"{SCHEMA_ROOT}/definition/page/2.1.0/schema.json",
                    "name": page,
                    "displayName": display,
                    "displayOption": "FitToPage",
                    "height": 720,
                    "width": 1280,
                },
                indent=2,
            )
            for page, display in PAGES[model.audience]
        },
        f"{model_dir}/definition.pbism": json.dumps({"version": "4.0", "settings": {}}, indent=2),
        f"{model_dir}/definition/database.tmdl": (
            f"database\n\tcompatibilityLevel: {COMPATIBILITY_LEVEL}\n"
        ),
        f"{model_dir}/definition/model.tmdl": (
            "model Model\n"
            "\tculture: en-US\n"
            "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
            "\tdiscourageImplicitMeasures\n"
            "\tsourceQueryCulture: en-US\n"
        ),
        f"{model_dir}/definition/expressions.tmdl": _expressions_tmdl(model.audience),
        f"{model_dir}/definition/relationships.tmdl": _relationships_tmdl(model),
    }
    for table in model.tables:
        files[f"{model_dir}/definition/tables/{table.name}.tmdl"] = table_tmdl(table)
    return {path: text if text.endswith("\n") else text + "\n" for path, text in files.items()}


def tmdl_script(model: Model) -> str:
    """The whole semantic model as one TMDL script, for the TMDL view of a blank report."""
    parts = [_expressions_tmdl(model.audience)]
    parts += [table_tmdl(table) for table in model.tables]
    parts.append(_relationships_tmdl(model))
    body = "\n".join(parts)
    indented = "\n".join(("\t" + line) if line else "" for line in body.splitlines())
    return (
        f"// ESG Lens India - {model.audience} model. Generated by scripts/build_powerbi.py.\n"
        "// Paste into TMDL view of a blank report and press Apply, then set ExportFolder.\n"
        "createOrReplace\n\n" + indented + "\n"
    )


def dax_file(model: Model) -> str:
    out = [
        f"// ESG Lens India - measures of the {model.audience} model.",
        "// Generated by scripts/build_powerbi.py; paste one at a time into New measure.",
        "",
    ]
    for table in model.tables:
        for measure in table.measures:
            out.append(f"// [{measure.folder}] {measure.description}")
            out.append(f"{measure.name} =")
            out += _expression(measure.expression, "    ")
            out.append("")
    return "\n".join(out)


def all_files(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    files: dict[str, str] = {}
    for model in (local_model(con), public_model(con)):
        project = f"esg_lens_{model.audience}"
        for path, text in project_files(model).items():
            files[f"{project}/{path}"] = text
        files[f"{project}.tmdl-script.tmdl"] = tmdl_script(model)
        files[f"{project}_measures.dax"] = dax_file(model)
    # exactly one newline at the end of every file, as the pre-commit hook wants it
    return {path: text.rstrip("\n") + "\n" for path, text in files.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db", type=Path, default=Path(os.getenv("DUCKDB_PATH") or export_bi.DEFAULT_DB)
    )
    parser.add_argument("--out", type=Path, default=POWERBI)
    parser.add_argument("--check", action="store_true", help="fail if the files differ")
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"warehouse not found: {args.db}")
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        files = all_files(con)
    finally:
        con.close()

    if args.check:
        stale = [
            path
            for path, text in files.items()
            if not (args.out / path).exists()
            or (args.out / path).read_text(encoding="utf-8") != text
        ]
        if stale:
            print("out of date (run python scripts/build_powerbi.py):\n  " + "\n  ".join(stale))
            return 1
        print(f"{len(files)} Power BI files up to date")
        return 0
    for path, text in files.items():
        target = args.out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(files)} files written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
