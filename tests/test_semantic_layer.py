"""The semantic layer (MetricFlow) is generated from the KPI catalogue and gives the same
numbers as plain SQL on the gold tables."""

from __future__ import annotations

import csv
import importlib.util
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT / "dbt"
YAML_FILE = DBT_DIR / "models" / "semantic" / "_semantic_layer.yml"
SAVED_QUERIES = DBT_DIR / "models" / "semantic" / "_saved_queries.yml"
WAREHOUSE = Path(os.getenv("DUCKDB_PATH") or ROOT / "data" / "warehouse" / "esg_lens.duckdb")
SCRIPTS = Path(sys.executable).parent
TOLERANCE = 1e-9
GROUP_BY = ["company_year__sector_group", "company_year__fiscal_year_label"]


def _module():
    spec = importlib.util.spec_from_file_location(
        "build_semantic_layer", ROOT / "scripts" / "build_semantic_layer.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metrics() -> dict[str, dict]:
    document = yaml.safe_load(YAML_FILE.read_text(encoding="utf-8"))
    return {
        metric["name"]: metric
        for model in document["models"]
        for metric in model.get("metrics", [])
    }


# ---------------------------------------------------------------- generated files and rules


def test_semantic_layer_is_generated_from_the_catalogue():
    assert _module().main(["--check"]) == 0, "run: python scripts/build_semantic_layer.py"


def test_every_catalogue_metric_is_in_the_yaml_with_its_publication_flag():
    module = _module()
    metrics = _metrics()
    rows = module.metric_rows(module.read_catalogue())
    assert 15 <= len(rows) <= 30
    for row in rows:
        metric = metrics[row["kpi_name"]]
        meta = metric["config"]["meta"]
        assert meta["public_safe"] is (row["public_safe"] == "true"), row["kpi_name"]
        assert not metric.get("hidden"), row["kpi_name"]
    for name, metric in metrics.items():
        assert isinstance(metric["config"]["meta"]["public_safe"], bool), name


def test_sums_of_filed_values_are_hidden_and_never_public():
    """Raw filed quantities only exist as hidden building blocks of a ratio."""
    for name, metric in _metrics().items():
        if metric.get("agg") == "sum" and name.endswith(("_num", "_den")):
            assert metric["hidden"] is True, name
            assert metric["config"]["meta"]["public_safe"] is False, name


def test_group_intensities_are_ratio_of_sums_or_median_never_an_average():
    module = _module()
    rows = module.metric_rows(module.read_catalogue())
    for row in rows:
        if row["unit_type"] in ("intensity", "pct"):
            assert row["metric_type"] in ("ratio_of_sums", "median", "share"), row["kpi_name"]
        if row["metric_type"] == "ratio_of_sums":
            assert row["kpi_name"].endswith("_agg")
            assert _metrics()[row["kpi_name"]]["type"] == "ratio"
        if row["metric_type"] == "median":
            assert row["kpi_name"].endswith("_median")
            assert _metrics()[row["kpi_name"]]["percentile"] == 0.5


def test_generator_refuses_an_average_of_company_intensities():
    module = _module()
    rows = module.read_catalogue()
    bad = dict(
        next(row for row in rows if row["kpi_name"] == "ghg_intensity_median"),
        kpi_name="ghg_intensity_avg",
        metric_type="average",
    )
    with pytest.raises(SystemExit, match="average of company intensities"):
        module.check_rules([*rows, bad])


def test_public_aggregates_over_filed_values_carry_the_five_company_rule():
    module = _module()
    metrics = _metrics()
    for row in module.metric_rows(module.read_catalogue()):
        if row["metric_type"] in ("ratio_of_sums", "median") and row["source_model"] == (
            "fct_company_year"
        ):
            meta = metrics[row["kpi_name"]]["config"]["meta"]
            assert meta["min_companies"] == 5, row["kpi_name"]
            assert metrics[meta["companies_metric"]]["agg"] == "count_distinct"


def test_saved_queries_use_known_metrics_and_show_the_company_count():
    metrics = _metrics()
    queries = yaml.safe_load(SAVED_QUERIES.read_text(encoding="utf-8"))["saved_queries"]
    assert 5 <= len(queries) <= 8
    for query in queries:
        names = query["query_params"]["metrics"]
        assert set(names) <= set(metrics), query["name"]
        assert not any(metrics[name].get("hidden") for name in names), query["name"]
    rule = next(q for q in queries if q["name"] == "public_rule_min_5_companies")
    gated = [
        name
        for name in rule["query_params"]["metrics"]
        if "min_companies" in metrics[name]["config"]["meta"]
    ]
    assert gated
    for name in gated:
        gate = metrics[name]["config"]["meta"]["companies_metric"]
        assert gate in rule["query_params"]["metrics"]


# ---------------------------------------------------------------- reconciliation with SQL


def _has_semantic_views() -> bool:
    if not WAREHOUSE.exists():
        return False
    import duckdb

    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        found = con.sql(
            "select count(*) from information_schema.tables where table_name in "
            "('sem_company_year', 'sem_disclosure_quality', 'sem_restatement', 'dim_company')"
        ).fetchone()[0]
        real = con.sql("select count(*) from dim_company").fetchone()[0] if found == 4 else 0
    finally:
        con.close()
    return found == 4 and real >= 40  # the real NIFTY 50 warehouse, not the synthetic one


def _run(exe: str, *args: str) -> None:
    env = os.environ | {
        "PYTHONUTF8": "1",  # the mf command prints symbols a Windows console cannot encode
        "ESG_DATA_DIR": os.getenv("ESG_DATA_DIR") or (ROOT / "data").as_posix(),
    }
    result = subprocess.run(
        [str(SCRIPTS / exe), *args],
        cwd=DBT_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, f"{exe} {' '.join(args)}\n{result.stdout}\n{result.stderr}"


def _mf_query(tmp_path: Path, *args: str) -> list[dict[str, str]]:
    out = tmp_path / "result.csv"
    _run("mf", "query", *args, "--csv", out.as_posix(), "--quiet")
    with out.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def semantic_manifest():
    if not _has_semantic_views():
        pytest.skip("needs the real warehouse with the semantic views (dev.ps1 dbt-build)")
    if not (SCRIPTS / "mf.exe").exists() and not (SCRIPTS / "mf").exists():
        pytest.skip("mf (dbt-metricflow) is not installed")
    # mf reads target/semantic_manifest.json: parse again only if the YAML is newer than it
    manifest = DBT_DIR / "target" / "semantic_manifest.json"
    sources = [YAML_FILE, SAVED_QUERIES, DBT_DIR / "dbt_project.yml"]
    if not manifest.exists() or manifest.stat().st_mtime < max(p.stat().st_mtime for p in sources):
        _run("dbt", "parse", "--profiles-dir", ".")


RECONCILED = [
    "ghg_intensity_agg",  # ratio of sums
    "renewable_share_agg",  # ratio of sums, in percent
    "ghg_intensity_median",  # median
    "dqs_avg",  # disclosure quality
    "dqs_median",
    "dqs_grade_a_share",
    "material_restatements",  # restatements
    "material_restatement_share",
    "companies_reporting",  # coverage
]

# The same figures written by hand on the gold tables, each by its own route to the sector group.
PLAIN_SQL = """
with company_year as (
    select
        sector_group,
        fiscal_year_label,
        sum(ghg_s12_tco2e) filter (where ghg_s12_tco2e is not null and turnover_cr <> 0)
        / sum(turnover_cr) filter (where ghg_s12_tco2e is not null and turnover_cr <> 0)
            as ghg_intensity_agg,
        100.0 * sum(energy_renewable_gj)
            filter (where energy_renewable_gj is not null and energy_total_gj <> 0)
        / sum(energy_total_gj)
            filter (where energy_renewable_gj is not null and energy_total_gj <> 0)
            as renewable_share_agg,
        median(ghg_intensity_tco2e_per_cr) as ghg_intensity_median,
        count(distinct isin) as companies_reporting
    from fct_company_year
    group by sector_group, fiscal_year_label
),

quality as (
    select
        sector_group,
        fiscal_year_label,
        avg(dqs_total) as dqs_avg,
        median(dqs_total) as dqs_median,
        100.0 * count(*) filter (where dqs_grade = 'A')
        / count(*) filter (where dqs_grade != 'insufficient_data') as dqs_grade_a_share
    from fct_disclosure_quality
    group by sector_group, fiscal_year_label
),

restatements as (
    select
        company.sector_group,
        restatement.value_fiscal_year_label as fiscal_year_label,
        count(*) filter (where restatement.classification = 'material') as material_restatements,
        100.0 * count(*) filter (where restatement.classification = 'material')
        / count(*) filter (where restatement.is_compared) as material_restatement_share
    from fct_restatement as restatement
    inner join dim_company as company on restatement.isin = company.isin
    group by company.sector_group, restatement.value_fiscal_year_label
)

select *
from company_year
left join quality using (sector_group, fiscal_year_label)
left join restatements using (sector_group, fiscal_year_label)
"""


def test_mf_query_matches_plain_sql_on_the_marts(semantic_manifest, tmp_path):
    import duckdb

    rows = _mf_query(tmp_path, "--metrics", ",".join(RECONCILED), "--group-by", ",".join(GROUP_BY))
    from_mf = {
        (row["company_year__sector_group"], row["company_year__fiscal_year_label"]): row
        for row in rows
    }
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        expected = con.sql(PLAIN_SQL).df().to_dict("records")
    finally:
        con.close()

    assert len(expected) == 12 and len(from_mf) == len(expected)  # 3 sector groups x 4 years
    compared = 0
    for record in expected:
        row = from_mf[(record["sector_group"], record["fiscal_year_label"])]
        for metric in RECONCILED:
            want, got = record[metric], row[metric]
            if want is None or (isinstance(want, float) and math.isnan(want)):
                assert got in ("", None), (metric, record, got)  # e.g. no restatements yet
                continue
            assert math.isclose(float(got), float(want), rel_tol=TOLERANCE, abs_tol=TOLERANCE), (
                metric,
                record["sector_group"],
                record["fiscal_year_label"],
                got,
                want,
            )
            compared += 1
    assert compared >= 100


def test_saved_query_shows_the_five_company_rule(semantic_manifest, tmp_path):
    """Consumers publish a gated figure only where its companies metric is 5 or more."""
    rows = _mf_query(tmp_path, "--saved-query", "public_rule_min_5_companies")
    assert rows
    counts = [int(float(row["companies_with_ghg_intensity"])) for row in rows]
    publishable = [row for row, n in zip(rows, counts, strict=True) if n >= 5]
    withheld = [row for row, n in zip(rows, counts, strict=True) if n < 5]
    assert publishable and withheld, "the real data has groups on both sides of the rule"
    assert {row["company_year__ranking_group"] for row in withheld} == {"Automobiles"}
    assert all(row["ghg_intensity_agg"] not in ("", None) for row in publishable)
