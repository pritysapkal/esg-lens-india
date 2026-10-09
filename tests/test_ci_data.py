"""scripts/make_ci_data.py builds the synthetic data folder used by the dbt CI job."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from ingestion import config


def _load_script():
    path = config.REPO_ROOT / "scripts" / "make_ci_data.py"
    spec = importlib.util.spec_from_file_location("make_ci_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_make_ci_data(tmp_path: Path) -> None:
    _load_script().build(tmp_path)

    manifest = pd.read_csv(tmp_path / "raw" / "manifest.csv", dtype=str)
    listing = pd.read_parquet(tmp_path / "processed" / "listing.parquet")
    universe = pd.read_csv(tmp_path / "raw" / "reference" / "ind_nifty50list.csv", dtype=str)
    assert manifest["filing_id"].tolist() == listing["filing_id"].tolist()
    assert universe["Symbol"].tolist() == ["EXAMPLE"]

    parsed = tmp_path / "processed" / "parsed"
    for table in ("filings", "contexts", "units", "facts", "text_facts"):
        files = list((parsed / table).glob("reporting_year_label=2025-2026/*.parquet"))
        assert len(files) == 1, table
    filings = pd.read_parquet(parsed / "filings")
    assert filings["n_facts"].tolist() == [14]
