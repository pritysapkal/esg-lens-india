"""Smoke tests: every ingestion module imports and the configured paths exist."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from ingestion import config

INGESTION_MODULES = [
    "ingestion",
    "ingestion.config",
    "ingestion.discover",
    "ingestion.instance",
    "ingestion.intake",
    "ingestion.parse_xbrl",
    "ingestion.taxonomy",
    "ingestion.todo",
    "ingestion.universe",
]


@pytest.mark.parametrize("module_name", INGESTION_MODULES)
def test_module_imports(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None


@pytest.mark.parametrize("path", config.DATA_PATHS, ids=lambda p: p.name)
def test_data_paths_exist(path) -> None:
    assert path.is_dir(), f"missing data directory: {path}"


def test_repo_paths_exist() -> None:
    assert config.XBRL_FIXTURES_DIR.is_dir()
    assert config.DOCS_DIR.is_dir()
    assert (config.DBT_DIR / "dbt_project.yml").is_file()


def test_duckdb_path_inside_warehouse_by_default() -> None:
    assert config.DUCKDB_PATH.suffix == ".duckdb"
    assert config.DUCKDB_PATH.parent.is_dir()


def test_duckdb_path_env_is_absolute_if_set() -> None:
    # dbt runs from dbt/ and also reads .env, so a relative DUCKDB_PATH would split the warehouse.
    value = os.environ.get("DUCKDB_PATH")
    if value:
        assert Path(value).is_absolute(), "DUCKDB_PATH must be absolute (see .env.example)"


def test_no_nse_network_code() -> None:
    # NSE terms of use forbid automated collection (docs/adr/0002): no HTTP client in ingestion.
    for path in (config.REPO_ROOT / "ingestion").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for needle in ("import httpx", "import requests", "urllib.request", "tenacity"):
            assert needle not in source, f"{path.name} contains {needle!r}"


def test_filing_id_is_stable_sha256() -> None:
    from ingestion.discover import filing_id_from_url

    url = "https://example.com/brsr/INE040A01034_2026.xml"
    assert filing_id_from_url(url) == filing_id_from_url(f"  {url} ")
    assert len(filing_id_from_url(url)) == 64
