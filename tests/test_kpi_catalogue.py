"""The KPI catalogue seed is the single source of truth: docs and publication flags follow it."""

from __future__ import annotations

import csv
import importlib.util
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "dbt" / "seeds" / "kpi_catalogue.csv"
MARTS_YML = ROOT / "dbt" / "models" / "marts" / "_marts.yml"
PUBLIC_SQL = ROOT / "dbt" / "models" / "marts" / "rpt_public_company_year.sql"
FACTS_WITH_POLICY = [
    "fct_company_year",
    "fct_esg_value",
    "fct_peer_benchmark",
    "fct_company_kpi_percentile",
    "fct_restatement",
]


def _catalogue() -> list[dict[str, str]]:
    with SEED.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _models() -> dict[str, dict]:
    doc = yaml.safe_load(MARTS_YML.read_text(encoding="utf-8"))
    return {model["name"]: model for model in doc["models"]}


def _public_safe(column: dict) -> bool | None:
    return column.get("config", {}).get("meta", {}).get("public_safe")


def test_kpi_docs_are_generated_from_the_seed():
    spec = importlib.util.spec_from_file_location(
        "build_kpi_docs", ROOT / "scripts" / "build_kpi_docs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0, "run: python scripts/build_kpi_docs.py"


def test_catalogue_rows_are_complete():
    rows = _catalogue()
    names = [row["kpi_name"] for row in rows]
    assert len(names) == len(set(names))
    for row in rows:
        assert row["label"] and row["formula_text"] and row["unit"] and row["definition_plain"]
        assert row["public_safe"] in {"true", "false"}


def test_every_fact_column_has_a_publication_flag():
    models = _models()
    for name in FACTS_WITH_POLICY:
        missing = [c["name"] for c in models[name]["columns"] if _public_safe(c) is None]
        assert not missing, f"{name}: columns without config.meta.public_safe: {missing}"


def test_fact_flags_follow_the_catalogue():
    safe = {row["kpi_name"]: row["public_safe"] == "true" for row in _catalogue()}
    columns = {c["name"]: _public_safe(c) for c in _models()["fct_company_year"]["columns"]}
    assert set(safe) <= set(columns), sorted(set(safe) - set(columns))
    wrong = {name for name, flag in safe.items() if columns[name] is not flag}
    assert not wrong, f"_marts.yml disagrees with kpi_catalogue.csv for: {sorted(wrong)}"


def test_public_model_selects_only_public_safe_columns():
    flags = {c["name"]: _public_safe(c) for c in _models()["fct_company_year"]["columns"]}
    sql = PUBLIC_SQL.read_text(encoding="utf-8")
    body = sql.split("select", 1)[1].split("from {{", 1)[0]
    selected = [part.strip() for part in body.split(",") if part.strip()]
    assert selected, "no columns found in rpt_public_company_year.sql"
    for column in selected:
        assert re.fullmatch(r"[a-z0-9_]+", column), f"unexpected expression: {column}"
        assert flags.get(column) is True, f"{column} is not public_safe in fct_company_year"
