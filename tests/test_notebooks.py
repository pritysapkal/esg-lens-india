"""Committed notebooks must not contain outputs (they would show real NSE-derived data)."""

from __future__ import annotations

import json

import pytest

from ingestion import config

NOTEBOOKS = sorted((config.REPO_ROOT / "notebooks").glob("*.ipynb"))


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_has_no_outputs(path) -> None:
    nb = json.loads(path.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [], f"{path.name}: clear outputs before committing"
            assert cell["execution_count"] is None
