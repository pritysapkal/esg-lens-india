"""The SQL business analysis (Week 10): every query runs and returns rows on synthetic gold
tables, its group figures agree with the semantic layer, and the published findings follow the
publication policy."""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT / "dbt"
SQL_DIR = ROOT / "analysis" / "sql"
FINDINGS = ROOT / "docs" / "analysis_findings.md"
MARTS_YML = DBT_DIR / "models" / "marts" / "_marts.yml"
WAREHOUSE = Path(os.getenv("DUCKDB_PATH") or ROOT / "data" / "warehouse" / "esg_lens.duckdb")
TOLERANCE = 1e-9
GOLD_TABLES = [
    "dim_company",
    "fct_company_year",
    "fct_esg_value",
    "fct_company_kpi_percentile",
    "fct_disclosure_quality",
    "fct_restatement",
]
HEADER_PARTS = ["Business question", "Stakeholder", "Method", "SQL techniques", "Caveats"]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up while it is being loaded
    spec.loader.exec_module(module)
    return module


RUNNER = _load("run_analysis")
QUERIES = RUNNER.load_queries()


# ------------------------------------------------------------------ synthetic gold tables

YEARS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
# ranking group -> (sector group, is GHG intensity ranked there)
GROUPS = {
    "Energy & utilities": ("Asset-heavy", True),
    "Consumer": ("Asset-light", True),
    "IT services": ("Asset-light", True),
    "Financials": ("Financials", False),
}
OWNERSHIP = ["Private Indian", "Government", "Private Indian", "MNC subsidiary", "Private Indian"]
# KPI -> True when a higher value is better
RANKED_KPIS = {
    "ghg_intensity_tco2e_per_cr": False,
    "energy_intensity_gj_per_cr": False,
    "water_intensity_kl_per_cr": False,
    "waste_intensity_t_per_cr": False,
    "renewable_share_pct": True,
    "waste_recovery_rate_pct": True,
}


def _company_years() -> pd.DataFrame:
    """Six made-up companies in each of four groups over four years, with the special cases the
    questions look for: a late entrant, a boundary change, a one-year spike, a 50% crossing."""
    rows = []
    for g, (group, (sector, _)) in enumerate(GROUPS.items()):
        for c in range(6):
            isin = f"INE{g}{c:02d}X01000"
            for y, year in enumerate(YEARS):
                if c == 5 and y == 0:
                    continue  # enters in the second year: outside the balanced panel
                turnover = 1000.0 * (g + 1) * (c + 1) * (1 + 0.1 * y * (1 if c != 4 else -1))
                emissions = turnover * (0.5 + 3 * (3 - g)) * (1 + c / 5) * (1 - 0.05 * y * (c % 3))
                if c == 2 and y == 1:
                    emissions *= 10  # a one-year spike that comes straight back
                energy = turnover * (2 + c)
                renewable_share = min(95.0, 20.0 + 12 * c + 9 * y)
                headcount = 5000.0 * (c + 1)
                women_share = 10.0 + 4 * g + c + 0.5 * y
                fatalities = float((c + y) % 3) if sector == "Asset-heavy" and c < 3 else 0.0
                rows.append(
                    {
                        "isin": isin,
                        "fiscal_year_label": year,
                        "filing_id": f"F{g}{c}{y}",
                        "symbol": f"SYN{g}{c}",
                        "display_name": f"Synthetic {group} {c}",
                        "peer_group": group,
                        "sector_group": sector,
                        "ranking_group": group,
                        "ownership_type": OWNERSHIP[(g + c) % len(OWNERSHIP)],
                        "has_comparability_break": c == 3 and y == 2,
                        "comparability_break_reason": "boundary change"
                        if c == 3 and y == 2
                        else None,
                        "period_months": 12,
                        "turnover_cr": turnover,
                        "ghg_s12_tco2e": emissions,
                        "ghg_intensity_tco2e_per_cr": emissions / turnover,
                        "scope3_disclosed": (c + y) % 4 != 0,
                        "energy_total_gj": energy,
                        "energy_renewable_gj": energy * renewable_share / 100,
                        "renewable_share_pct": renewable_share,
                        "energy_intensity_gj_per_cr": energy / turnover,
                        "water_intensity_kl_per_cr": 3.0 + c + 0.1 * y,
                        "waste_intensity_t_per_cr": 1.0 + ((c * 7) % 5) + 0.1 * y,
                        "waste_recovery_rate_pct": 30.0 + 10 * ((c * 3) % 6),
                        "headcount_total": headcount,
                        "headcount_female": headcount * women_share / 100,
                        "female_workforce_pct": women_share,
                        "pay_equity_gap_pp": None if y == 0 else -6.0 + c + 0.4 * y * (1 - c % 2),
                        "fatalities_total": fatalities,
                        "any_fatality": fatalities > 0,
                        "fatalities_per_10k_workforce": 10000 * fatalities / headcount,
                    }
                )
    return pd.DataFrame(rows)


def _percentiles(company_years: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (group, year), frame in company_years.groupby(["ranking_group", "fiscal_year_label"]):
        material = GROUPS[group][1]
        for kpi, higher_better in RANKED_KPIS.items():
            position = frame[kpi].rank(ascending=higher_better, method="min") - 1
            for (_, row), rank in zip(frame.iterrows(), position, strict=True):
                ranked = material and len(frame) >= 5
                rows.append(
                    {
                        "isin": row["isin"],
                        "fiscal_year_label": year,
                        "kpi_name": kpi,
                        "ranking_group": group,
                        "value": row[kpi],
                        "group_n": len(frame),
                        "percentile_in_group": (
                            round(100 * rank / (len(frame) - 1), 1) if ranked else None
                        ),
                        "percentile_null_reason": (
                            None if ranked else ("not_material" if not material else "group_n_lt_5")
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _disclosure_quality(company_years: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for index, row in company_years.reset_index(drop=True).iterrows():
        y = YEARS.index(row["fiscal_year_label"])
        score = 70.0 + (index * 7) % 25 + 2.0 * y * (index % 3)
        rows.append(
            {
                **{
                    key: row[key]
                    for key in [
                        "isin",
                        "fiscal_year_label",
                        "symbol",
                        "display_name",
                        "peer_group",
                        "sector_group",
                        "ranking_group",
                    ]
                },
                "dqs_total": min(score, 100.0),
                "dqs_grade": "A" if score >= 85 else "B",
                "dqs_components_used": 4 if y in (1, 2) else 3,
                "is_provisional": y == 3,
            }
        )
    return pd.DataFrame(rows)


def _restatements(company_years: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metrics = ["ghg_scope1_tco2e", "ghg_scope2_tco2e", "water_consumption_kl", "ltifr"]
    observable = company_years[company_years["fiscal_year_label"] != YEARS[-1]]
    for index, row in observable.reset_index(drop=True).iterrows():
        for m, metric in enumerate(metrics):
            material = (index + m) % 5 == 0
            scale_error = (index + m) % 17 == 0 and not material
            rows.append(
                {
                    "isin": row["isin"],
                    "symbol": row["symbol"],
                    "metric_id": metric,
                    "dimension_key": "",
                    "value_fiscal_year_label": row["fiscal_year_label"],
                    "restating_filing_id": f"R{index}{m}",
                    "classification": (
                        "material"
                        if material
                        else ("suspected_scale_error" if scale_error else "no_change")
                    ),
                    "is_compared": not scale_error,
                    "flatters_trend": (index % 2 == 0) if material else None,
                }
            )
    return pd.DataFrame(rows)


def _contract_columns() -> dict[str, dict[str, str]]:
    """Column names and types of the gold tables, as enforced by the dbt contracts."""
    models = yaml.safe_load(MARTS_YML.read_text(encoding="utf-8"))["models"]
    return {
        model["name"]: {column["name"]: column["data_type"] for column in model["columns"]}
        for model in models
        if model["name"] in GOLD_TABLES
    }


def synthetic_frames() -> dict[str, pd.DataFrame]:
    """Made-up rows for the gold tables the analysis reads. No real company, no filed value."""
    company_years = _company_years()
    companies = company_years.drop_duplicates("isin")[
        ["isin", "display_name", "peer_group", "sector_group", "ranking_group", "ownership_type"]
    ].assign(current_name=lambda d: d["display_name"], current_symbol=lambda d: d["isin"].str[3:6])
    esg_values = pd.DataFrame(
        [
            {
                "isin": company_years["isin"].iloc[0],
                "metric_id": "ghg_scope1_tco2e",
                "value_fiscal_year_label": YEARS[0],
                "dimension_key": "",
                "source_filing_id": "F000",
                "best_value_source": "replaced_by_later_comparative",
                "is_latest_value": True,
            }
        ]
    )
    return {
        "dim_company": companies,
        "fct_company_year": company_years,
        "fct_esg_value": esg_values,
        "fct_company_kpi_percentile": _percentiles(company_years),
        "fct_disclosure_quality": _disclosure_quality(company_years),
        "fct_restatement": _restatements(company_years),
    }


def build_synthetic_gold(
    con: duckdb.DuckDBPyConnection, frames: dict[str, pd.DataFrame] | None = None
) -> None:
    """Create the gold tables with the real column names and types (from the dbt contracts in
    _marts.yml) and the made-up rows of `frames` (default: `synthetic_frames`)."""
    frames = frames or synthetic_frames()
    contracts = _contract_columns()
    assert set(contracts) == set(GOLD_TABLES)
    for table, columns in contracts.items():
        frame = frames[table]
        unknown = set(frame.columns) - set(columns)
        assert not unknown, f"{table}: fixture columns not in the contract: {sorted(unknown)}"
        frame = frame.astype(object).where(frame.notna(), None)
        con.register("fixture_frame", frame)
        select = ", ".join(
            f"cast({name} as {dtype}) as {name}"
            if name in frame.columns
            else f"cast(null as {dtype}) as {name}"
            for name, dtype in columns.items()
        )
        con.execute(f"create table {table} as select {select} from fixture_frame")
        con.unregister("fixture_frame")


@pytest.fixture(scope="module")
def synthetic_results() -> dict[str, pd.DataFrame]:
    con = duckdb.connect(":memory:")
    try:
        build_synthetic_gold(con)
        return RUNNER.run_queries(con, QUERIES)
    finally:
        con.close()


# ------------------------------------------------------------------ the question files


def test_there_are_twelve_question_files_with_a_full_header():
    files = sorted(SQL_DIR.glob("q[0-9][0-9]_*.sql"))
    assert [path.name[:3] for path in files] == [f"q{n:02d}" for n in range(1, 13)]
    for path in files:
        header = path.read_text(encoding="utf-8").split("-- result:", 1)[0]
        assert header.startswith(f"-- Q{int(path.name[1:3])}. "), path.name
        for part in HEADER_PARTS:
            assert f"-- {part}" in header, f"{path.name}: header has no '{part}'"


@pytest.mark.parametrize("query", QUERIES, ids=lambda query: query.result_id)
def test_every_query_runs_and_returns_rows_on_synthetic_data(query, synthetic_results):
    frame = synthetic_results[query.result_id]
    assert len(frame) > 0, f"{query.result_id} returned no rows"
    assert len(frame.columns) >= 3


def test_group_statistics_respect_the_five_company_rule(synthetic_results):
    """No group intensity, share or median where fewer than 5 companies stand behind it."""
    checks = {
        "q01_decarbonisation__ghg_intensity_by_sector": ("n_companies", "ghg_intensity_agg"),
        "q04_renewable_share__renewable_share_by_peer_group": (
            "n_companies",
            "renewable_share_agg_pct",
        ),
        "q08_disclosure_quality__dqs_median_by_sector_and_ownership": ("n_companies", "dqs_median"),
        "q12_safety__fatality_rate_by_sector_group": (
            "n_companies",
            "fatalities_per_10k_workforce_agg",
        ),
    }
    small_groups_seen = 0
    for result_id, (count, statistic) in checks.items():
        frame = synthetic_results[result_id]
        small = frame[frame[count] < 5]
        small_groups_seen += len(small)
        assert small[statistic].isna().all(), result_id
    assert small_groups_seen > 0, "the synthetic data should contain groups below 5 companies"


def test_q3_ranks_only_pairs_confirmed_by_a_later_report(synthetic_results):
    frame = synthetic_results["q03_ghg_leaders_laggards__yoy_changes_with_confidence"]
    ranked = frame[frame["is_ranked"]]
    assert len(ranked) > 0 and set(ranked["confidence"]) == {"confirmed"}
    assert (ranked["n_companies_compared"] >= 5).all()
    unranked = frame[~frame["is_ranked"]]
    assert unranked["improvement_rank_in_group"].isna().all()
    assert unranked["improvement_rank_overall"].isna().all()
    # the latest year has no later report: every pair that ends there is provisional
    latest = frame["to_year"].max()
    at_the_end = frame[frame["to_year"] == latest]
    assert set(at_the_end["confidence"]) <= {"provisional", "one_year_reversal"}
    assert "one_year_reversal" in set(frame["confidence"])  # the spike planted in the fixture


def test_q5_sets_implausible_changes_aside(synthetic_results):
    frame = synthetic_results["q05_decoupling__decoupling_by_company"]
    review = frame[frame["decoupling_class"] == "needs_review"]
    assert len(review) > 0 and review["review_reason"].notna().all()
    assert frame[frame["decoupling_class"] != "needs_review"]["review_reason"].isna().all()
    plausible = frame[frame["decoupling_class"] != "needs_review"]
    assert plausible["turnover_change_pct"].between(-50, 100).all()
    assert plausible["emissions_change_pct"].between(-50, 100).all()
    by_group = synthetic_results["q05_decoupling__decoupling_by_sector_group"]
    total = by_group[by_group["sector_group"] == "All sector groups"]
    assert total["n_companies"].sum() == total["n_companies_before_screen"].sum() == len(frame)


def test_no_query_averages_company_ratios_into_a_group_intensity():
    forbidden = re.compile(r"avg\(\s*\w*\.?\w*(intensity|_pct|_share)\w*\s*\)", re.IGNORECASE)
    for query in QUERIES:
        assert not forbidden.search(query.sql), f"{query.result_id}: average of company ratios"


# ------------------------------------------------------------------ reconciliation with mf


def _mf_batch(batch: list[list[str]]) -> None:
    semantic = _load_test_module("test_semantic_layer")
    env = os.environ | {
        "PYTHONUTF8": "1",
        "ESG_DATA_DIR": os.getenv("ESG_DATA_DIR") or (ROOT / "data").as_posix(),
    }
    result = subprocess.run(
        [sys.executable, "-c", semantic.MF_BATCH, json.dumps(batch)],
        cwd=DBT_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _load_test_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_q1_and_q8_headline_numbers_match_mf_query(tmp_path):
    """Q1 (GHG intensity, whole group and typical company, all companies) and Q8 (median DQS by
    sector group, by ownership type and overall) against the semantic layer."""
    semantic = _load_test_module("test_semantic_layer")
    if not semantic._has_semantic_views():
        pytest.skip("needs the real warehouse with the semantic views (dev.ps1 dbt-build)")
    manifest = DBT_DIR / "target" / "semantic_manifest.json"
    if not manifest.exists():
        semantic._run("dbt", "parse", "--profiles-dir", ".")

    year = "company_year__fiscal_year_label"
    outputs = {name: tmp_path / f"{name}.csv" for name in ("q1", "q8_sector", "q8_owner", "q8_all")}
    _mf_batch(
        [
            [
                "--metrics",
                "ghg_intensity_agg,ghg_intensity_median",
                "--group-by",
                f"company_year__sector_group,{year}",
                "--csv",
                outputs["q1"].as_posix(),
            ],
            [
                "--metrics",
                "dqs_median",
                "--group-by",
                f"company_year__sector_group,{year}",
                "--csv",
                outputs["q8_sector"].as_posix(),
            ],
            [
                "--metrics",
                "dqs_median",
                "--group-by",
                f"company_year__ownership_type,{year}",
                "--csv",
                outputs["q8_owner"].as_posix(),
            ],
            ["--metrics", "dqs_median", "--group-by", year, "--csv", outputs["q8_all"].as_posix()],
        ]
    )

    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        results = RUNNER.run_queries(con, [q for q in QUERIES if q.file.startswith(("q01", "q08"))])
    finally:
        con.close()

    compared = 0

    def same(got: str, want: float, where: tuple) -> None:
        nonlocal compared
        assert math.isclose(float(got), float(want), rel_tol=TOLERANCE, abs_tol=TOLERANCE), (
            where,
            got,
            want,
        )
        compared += 1

    # Q1: the all-companies panel is the semantic layer's population
    from_mf = {(r["company_year__sector_group"], r[year]): r for r in _read_csv(outputs["q1"])}
    q1 = results["q01_decarbonisation__ghg_intensity_by_sector"]
    q1 = q1[q1["panel"] == "all companies"]
    assert len(q1) == len(from_mf) == 12
    for row in q1.to_dict("records"):
        key = (row["sector_group"], row["fiscal_year_label"])
        same(from_mf[key]["ghg_intensity_agg"], row["ghg_intensity_agg_exact"], ("q1 agg", key))
        same(
            from_mf[key]["ghg_intensity_median"],
            row["ghg_intensity_median_exact"],
            ("q1 median", key),
        )

    # Q8: the three subtotal levels of the GROUPING SETS query
    q8 = results["q08_disclosure_quality__dqs_median_by_sector_and_ownership"]
    levels = {
        "sector group": ("q8_sector", "company_year__sector_group", "sector_group"),
        "ownership type": ("q8_owner", "company_year__ownership_type", "ownership_type"),
        "all companies": ("q8_all", None, None),
    }
    for level, (output, mf_column, column) in levels.items():
        from_mf = {
            (r[mf_column] if mf_column else "all", r[year]): r for r in _read_csv(outputs[output])
        }
        rows = q8[(q8["subtotal_level"] == level) & q8["dqs_median_exact"].notna()]
        assert len(rows) > 0
        for row in rows.to_dict("records"):
            key = (row[column] if column else "all", row["fiscal_year_label"])
            same(from_mf[key]["dqs_median"], row["dqs_median_exact"], (level, key))

    print(f"\nQ1 and Q8 against mf query: {compared} figures compared, all equal within 1e-9")
    assert compared >= 40


# ------------------------------------------------------------------ the published findings

# a number followed by a unit of a filed quantity, not followed by "per": a raw value
RAW_VALUE = re.compile(
    r"\d[\d,.]*\s*(million|lakh|crore)?\s*"
    r"(tCO2e|tonnes of|tonnes\b|GJ\b|TJ\b|kl\b|kilolitres|MWh|employees\b|workers\b|deaths\b)"
    r"(?!\s*(per|/))",
    re.IGNORECASE,
)
MONEY = re.compile(r"(Rs\.?|INR|₹)\s*\d", re.IGNORECASE)


def test_findings_cover_every_question_and_link_its_sql():
    text = FINDINGS.read_text(encoding="utf-8")
    for path in sorted(SQL_DIR.glob("q[0-9][0-9]_*.sql")):
        assert f"../analysis/sql/{path.name}" in text, f"no link to {path.name}"
    for heading in ("## Executive summary", "## SQL techniques used"):
        assert heading in text
    for label in ("**Question.**", "**Answer.**", "**So what.**", "**Caveat.**"):
        assert text.count(label) == 12, label


def test_findings_follow_the_publication_policy():
    """Derived values only: no raw filed quantity, no amount in rupees, no link to the exchange."""
    text = FINDINGS.read_text(encoding="utf-8")
    raw = [match.group(0) for match in RAW_VALUE.finditer(text)]
    assert not raw, f"raw filed quantities in the findings: {raw}"
    money = [match.group(0) for match in MONEY.finditer(text)]
    assert not money, f"amounts in rupees in the findings: {money}"
    assert "nseindia" not in text.lower() and "http" not in text.lower()
    assert "not an ESG rating" in text and "not investment advice" in text
