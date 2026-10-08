"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion import config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return config.REPO_ROOT


@pytest.fixture(scope="session")
def synthetic_xml() -> Path:
    """Hand-written synthetic BRSR instance (fake company, fake ISIN)."""
    return FIXTURES / "synthetic_brsr.xml"


@pytest.fixture(scope="session")
def listing_sample_csv() -> Path:
    """Three made-up listing rows in the real NSE CSV format (BOM, header quirks)."""
    return FIXTURES / "listing_sample.csv"
