"""Reconcile the Power BI measures with the semantic layer (Week 12).

    python scripts/reconcile_bi.py

Power BI cannot be run from a script, so each checked measure is computed here in pandas with
the same formula as its DAX (scripts/build_powerbi.py), on the same Parquet files Power BI
loads (exports/local), joined the way the model's relationships join them (dimensions by isin
and fiscal year). The result is compared with `mf query` on the semantic layer, figure by
figure, within 1e-9. The public model is checked too: its group measures read
rpt_public_group_metrics, which must hold the same figures wherever it shows one.

The six figures Prity checks by hand in Power BI Desktop are listed in
docs/powerbi_reconciliation.md; `checklist()` gives their expected values.
"""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT / "dbt"
LOCAL = ROOT / "exports" / "local"
PUBLIC = ROOT / "exports" / "public"
TOLERANCE = 1e-9
# exports/public is rounded to this many decimals by export_bi.py (PUBLIC_DECIMALS); a public
# figure is compared with the local figure rounded the same way
PUBLIC_DECIMALS = 6
YEAR = "company_year__fiscal_year_label"

MF_BATCH = """
import json, sys
from click.testing import CliRunner
from dbt_metricflow.cli.cli_configuration import CLIConfiguration
from dbt_metricflow.cli.main import cli

configuration, runner = CLIConfiguration(), CliRunner()
for arguments in json.loads(sys.argv[1]):
    result = runner.invoke(cli, ["query", *arguments, "--quiet"], obj=configuration)
    if result.exit_code != 0:
        sys.exit(f"mf query {arguments}: {result.output} {result.exception!r}")
"""

# measure (Power BI name) -> (semantic-layer metric, group-by dimension or None)
CHECKS = {
    "GHG intensity (whole group)": ("ghg_intensity_agg", "sector_group"),
    "GHG intensity (typical company)": ("ghg_intensity_median", "sector_group"),
    "Renewable share (whole group, %)": ("renewable_share_agg", "peer_group"),
    "DQS median": ("dqs_median", "sector_group"),
    "Grade A share (%)": ("dqs_grade_a_share", "sector_group"),
    "Material restatement share (%)": ("material_restatement_share", None),
}


# ------------------------------------------------------------------ the DAX, in pandas


def _ratio_of_sums(rows: pd.DataFrame, numerator: str, denominator: str, scale: float = 1):
    """DIVIDE(SUMX(rows_with_both, num), SUMX(rows_with_both, den)): rows with a numerator
    and a non-zero denominator (a blank denominator is not <> 0 in DAX either)."""
    both = rows[rows[numerator].notna() & rows[denominator].notna() & (rows[denominator] != 0)]
    denominator_sum = both[denominator].sum()
    return math.nan if denominator_sum == 0 else scale * both[numerator].sum() / denominator_sum


def _median(rows: pd.DataFrame, column: str):
    """MEDIANX(FILTER(table, NOT ISBLANK(column)), column)."""
    values = rows[column].dropna()
    return math.nan if values.empty else float(values.median())


def _grade_a_share(rows: pd.DataFrame):
    graded = rows[rows["dqs_grade"].notna() & (rows["dqs_grade"] != "insufficient_data")]
    return math.nan if graded.empty else 100 * (rows["dqs_grade"] == "A").sum() / len(graded)


def _restatement_share(rows: pd.DataFrame):
    compared = rows["is_compared"].fillna(False).astype(bool).sum()
    material = (rows["classification"] == "material").sum()
    return math.nan if compared == 0 else 100 * material / compared


def load_local(folder: Path = LOCAL) -> dict[str, pd.DataFrame]:
    tables = {
        name: pd.read_parquet(folder / f"{name}.parquet")
        for name in ("dim_company", "fct_company_year", "fct_disclosure_quality", "fct_restatement")
    }
    groups = tables["dim_company"][["isin", "sector_group", "peer_group", "in_ghg_balanced_panel"]]
    # the model filters facts through dim_company, so group by the dimension's columns
    for name in ("fct_company_year", "fct_disclosure_quality", "fct_restatement"):
        facts = tables[name].drop(columns=["sector_group", "peer_group"], errors="ignore")
        tables[name] = facts.merge(groups, on="isin", how="left")
    tables["fct_restatement"] = tables["fct_restatement"].rename(
        columns={"value_fiscal_year_label": "fiscal_year_label"}
    )
    return tables


def dax_equivalent(tables: dict[str, pd.DataFrame]) -> dict[str, dict[tuple, float]]:
    """{measure: {(group, year): value}} with the formula of each DAX measure."""
    formulas = {
        "GHG intensity (whole group)": (
            "fct_company_year",
            lambda r: _ratio_of_sums(r, "ghg_s12_tco2e", "turnover_cr"),
        ),
        "GHG intensity (typical company)": (
            "fct_company_year",
            lambda r: _median(r, "ghg_intensity_tco2e_per_cr"),
        ),
        "Renewable share (whole group, %)": (
            "fct_company_year",
            lambda r: _ratio_of_sums(r, "energy_renewable_gj", "energy_total_gj", 100),
        ),
        "DQS median": ("fct_disclosure_quality", lambda r: _median(r, "dqs_total")),
        "Grade A share (%)": ("fct_disclosure_quality", _grade_a_share),
        "Material restatement share (%)": ("fct_restatement", _restatement_share),
    }
    results: dict[str, dict[tuple, float]] = {}
    for measure, (table, formula) in formulas.items():
        group = CHECKS[measure][1]
        keys = [group, "fiscal_year_label"] if group else ["fiscal_year_label"]
        results[measure] = {
            (key if isinstance(key, tuple) else (key,)): formula(rows)
            for key, rows in tables[table].groupby(keys, dropna=True)
        }
    return results


# ------------------------------------------------------------------ the semantic layer


def mf_values(workdir: Path) -> dict[str, dict[tuple, float]]:
    """The same figures from `mf query` (needs the real warehouse and dbt/target)."""
    batch, outputs = [], {}
    for measure, (metric, group) in CHECKS.items():
        outputs[measure] = workdir / f"{metric}.csv"
        group_by = f"company_year__{group},{YEAR}" if group else YEAR
        batch.append(
            ["--metrics", metric, "--group-by", group_by, "--csv", outputs[measure].as_posix()]
        )
    env = os.environ | {
        "PYTHONUTF8": "1",
        "ESG_DATA_DIR": os.getenv("ESG_DATA_DIR") or (ROOT / "data").as_posix(),
    }
    result = subprocess.run(
        [sys.executable, "-c", MF_BATCH, json.dumps(batch)],
        cwd=DBT_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"mf query failed:\n{result.stdout}\n{result.stderr}")
    values: dict[str, dict[tuple, float]] = {}
    for measure, (metric, group) in CHECKS.items():
        with outputs[measure].open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        values[measure] = {
            ((row[f"company_year__{group}"], row[YEAR]) if group else (row[YEAR],)): (
                float(row[metric]) if row[metric] not in ("", None) else math.nan
            )
            for row in rows
        }
    return values


def compare(ours: dict, theirs: dict) -> tuple[int, float, list[str]]:
    """(figures compared, largest difference, problems)."""
    compared, largest, problems = 0, 0.0, []
    for measure, expected in theirs.items():
        got = ours[measure]
        if set(got) != set(expected):
            problems.append(f"{measure}: groups differ {sorted(set(got) ^ set(expected))[:5]}")
        for key in set(got) & set(expected):
            a, b = got[key], expected[key]
            if math.isnan(a) and math.isnan(b):
                continue
            difference = abs(a - b)
            largest = max(largest, difference)
            compared += 1
            if not math.isclose(a, b, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
                problems.append(f"{measure} {key}: Power BI formula {a} vs mf {b}")
    return compared, largest, problems


def public_matches(ours: dict, folder: Path = PUBLIC) -> tuple[int, list[str]]:
    """Every figure rpt_public_group_metrics shows equals the local DAX-equivalent figure,
    rounded to the decimals of the public export."""
    table = pd.read_parquet(folder / "rpt_public_group_metrics.parquet")
    compared, problems = 0, []
    for measure, (metric, group) in CHECKS.items():
        group_type = group or "all"
        rows = table[(table["group_type"] == group_type) & table[metric].notna()]
        for row in rows.itertuples():
            key = (row.group_value, row.fiscal_year_label) if group else (row.fiscal_year_label,)
            value = getattr(row, metric)
            expected = round(ours[measure][key], PUBLIC_DECIMALS)
            compared += 1
            if not math.isclose(value, expected, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
                problems.append(f"public {measure} {key}: {value} vs {expected}")
    return compared, problems


# ------------------------------------------------------------------ the hand checklist


def checklist(tables: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    """The six figures to verify in Power BI Desktop, with their expected values."""
    cy, dq, rs = (
        tables["fct_company_year"],
        tables["fct_disclosure_quality"],
        tables["fct_restatement"],
    )
    latest = cy["fiscal_year_label"].max()
    years = sorted(cy["fiscal_year_label"].unique())
    final = years[-2] if len(years) > 1 else latest
    first_with_restatements = years[1] if len(years) > 2 else years[0]
    heavy = cy[(cy["sector_group"] == "Asset-heavy") & (cy["fiscal_year_label"] == latest)]
    it = cy[(cy["peer_group"] == "IT services") & (cy["fiscal_year_label"] == latest)]
    return [
        {"measure": "Companies in selection", "filters": f"Year = {latest}",
         "expected": cy.loc[cy["fiscal_year_label"] == latest, "isin"].nunique(), "format": "0"},
        {"measure": "GHG intensity (whole group)", "filters": f"Year = {latest}, sector group = Asset-heavy",
         "expected": _ratio_of_sums(heavy, "ghg_s12_tco2e", "turnover_cr"), "format": "0.00"},
        {"measure": "GHG intensity (typical company)", "filters": f"Year = {latest}, sector group = Asset-heavy",
         "expected": _median(heavy, "ghg_intensity_tco2e_per_cr"), "format": "0.00"},
        {"measure": "Renewable share (whole group, %)", "filters": f"Year = {latest}, peer group = IT services",
         "expected": _ratio_of_sums(it, "energy_renewable_gj", "energy_total_gj", 100), "format": "0.0"},
        {"measure": "DQS median", "filters": f"Year = {final}, no other filter",
         "expected": _median(dq[dq["fiscal_year_label"] == final], "dqs_total"), "format": "0.00"},
        {"measure": "Material restatement share (%)", "filters": f"Year = {first_with_restatements}",
         "expected": _restatement_share(rs[rs["fiscal_year_label"] == first_with_restatements]), "format": "0.0"},
    ]  # fmt: skip


def public_checklist(folder: Path = PUBLIC) -> list[dict[str, object]]:
    """Figures to check in the PUBLIC model, read from the public files the model loads (the
    measures only pick these values; nothing is recomputed)."""
    groups = pd.read_parquet(folder / "rpt_public_group_metrics.parquet")
    concentration = pd.read_parquet(folder / "rpt_public_concentration.parquet")
    percentiles = pd.read_parquet(folder / "rpt_public_company_percentile.parquet")
    years = sorted(groups["fiscal_year_label"].unique())
    latest, final = years[-1], years[-2]

    def group(group_type: str, value: str, year: str, column: str):
        row = groups[
            (groups["group_type"] == group_type)
            & (groups["group_value"] == value)
            & (groups["fiscal_year_label"] == year)
        ]
        return row[column].iloc[0]

    in_year = concentration[concentration["fiscal_year_label"] == latest]
    asian = percentiles[
        (percentiles["display_name"] == "Asian Paints")
        & (percentiles["fiscal_year_label"] == final)
        & (percentiles["kpi_name"] == "ghg_intensity_tco2e_per_cr")
    ].iloc[0]
    banks = percentiles[
        (percentiles["ranking_group"] == "Financials")
        & (percentiles["fiscal_year_label"] == final)
        & (percentiles["kpi_name"] == "ghg_intensity_tco2e_per_cr")
    ]
    return [
        {"page": 1, "measure": "Companies reporting", "filters": f"group type all, {latest}",
         "expected": group("all", "All companies", latest, "companies_reporting"), "format": "0"},
        {"page": 2, "measure": "GHG intensity, whole group", "filters": f"group type sector_group, Asset-heavy, {latest}",
         "expected": group("sector_group", "Asset-heavy", latest, "ghg_intensity_agg"), "format": "0.00"},
        {"page": 2, "measure": "GHG intensity, typical company", "filters": f"group type sector_group, Asset-heavy, {latest}",
         "expected": group("sector_group", "Asset-heavy", latest, "ghg_intensity_median"), "format": "0.00"},
        {"page": 3, "measure": "Top-5 share of emissions (%)", "filters": f"{latest}",
         "expected": in_year.loc[in_year["emitter_rank"] == 5, "cumulative_share_pct"].iloc[0], "format": "0.0"},
        {"page": 3, "measure": "Companies for 80% of emissions", "filters": f"{latest}",
         "expected": int((in_year["cumulative_share_pct"] < 80).sum()) + 1, "format": "0"},
        {"page": 4, "measure": "Disclosure Quality Score, typical company", "filters": f"group type all, {final}",
         "expected": group("all", "All companies", final, "dqs_median"), "format": "0.00"},
        {"page": 5, "measure": "Company: peer percentile", "filters": f"Asian Paints, {final}, GHG intensity row",
         "expected": asian["percentile_in_group"], "format": "0.0"},
        {"page": 5, "measure": "Company: rank in group", "filters": f"Asian Paints, {final}, GHG intensity row",
         "expected": asian["rank_in_group"], "format": "0"},
        {"page": 5, "measure": "Ranking note: GHG intensity", "filters": f"group type ranking_group, Financials, {final}",
         "expected": "not ranked for this group (not material)" if (banks["reason_not_ranked"] == "not_material").any() else "",
         "format": "text"},
    ]  # fmt: skip


def main() -> int:
    tables = load_local()
    ours = dax_equivalent(tables)
    with tempfile.TemporaryDirectory() as workdir:
        theirs = mf_values(Path(workdir))
    compared, largest, problems = compare(ours, theirs)
    public_compared, public_problems = public_matches(ours)
    for measure, (metric, group) in CHECKS.items():
        print(
            f"{measure:<36} = mf {metric:<28} by {group or 'year':<13} {len(theirs[measure]):>3} figures"
        )
    print(
        f"local model: {compared} figures compared with mf query, largest difference {largest:.3g}"
    )
    print(f"public model: {public_compared} shown figures of rpt_public_group_metrics compared")
    print("\nchecklist for Power BI Desktop:")
    for item in checklist(tables):
        print(f"  {item['measure']:<36} {item['filters']:<45} {item['expected']:.4f}")
    for problem in problems + public_problems:
        print("PROBLEM", problem)
    return 1 if problems or public_problems else 0


if __name__ == "__main__":
    sys.exit(main())
