"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion import config


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return config.REPO_ROOT


@pytest.fixture(scope="session")
def xbrl_fixtures_dir() -> Path:
    return config.XBRL_FIXTURES_DIR


@pytest.fixture(scope="session")
def hdfc_brsr_xml(xbrl_fixtures_dir: Path) -> Path:
    """HDFC Bank FY2025-26 BRSR instance; skips the test until the file is added."""
    candidates = sorted(xbrl_fixtures_dir.glob("*.xml"))
    if not candidates:
        pytest.skip("No XBRL fixture in fixtures/xbrl/ yet")
    return candidates[0]
