"""Repository safety: no API key or other secret is tracked by git, the files that hold secrets
are ignored, and every public model is covered by the publication rules (Week 13 fixes)."""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Patterns of things that look like credentials. The values in tests are made up and short or
# obviously fake, so they do not match.
KEY_LIKE = [
    re.compile(rb"sk-ant-[A-Za-z0-9_\-]{16,}"),  # Anthropic API / admin keys
    re.compile(rb"sk-[A-Za-z0-9]{32,}"),  # other providers' secret keys
    re.compile(rb"(?i)anthropic_api_key\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{16,}"),
    re.compile(
        rb"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*[\"'][A-Za-z0-9_\-/+]{20,}[\"']"
    ),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(rb"ghp_[A-Za-z0-9]{30,}"),  # GitHub token
]
SECRET_FILES = [".env", ".env.local", ".streamlit/secrets.toml", "app/.streamlit/secrets.toml"]
BINARY = {".parquet", ".xlsx", ".pbix", ".zip", ".gz", ".png", ".jpg", ".pdf", ".duckdb"}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def tracked() -> list[str]:
    if (
        not shutil.which("git")
        or _git("rev-parse", "--is-inside-work-tree").stdout.strip() != "true"
    ):
        pytest.skip("not a git checkout")
    return [line for line in _git("ls-files", "-z").stdout.split("\0") if line]


def test_no_tracked_file_holds_anything_key_like(tracked):
    found = []
    for name in tracked:
        path = ROOT / name
        if path.suffix.lower() in BINARY or not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        content = path.read_bytes()
        found += [
            f"{name}: {pattern.pattern[:30]!r}" for pattern in KEY_LIKE if pattern.search(content)
        ]
    assert not found, f"key-like content in tracked files: {found}"


def test_files_that_hold_secrets_are_ignored_and_untracked(tracked):
    for name in SECRET_FILES:
        assert name not in tracked, f"{name} is tracked"
        assert _git("check-ignore", "-q", name).returncode == 0, f"{name} is not in .gitignore"
    assert ".env.example" in tracked  # the template stays, and holds no key
    assert "ANTHROPIC_API_KEY=" not in (ROOT / ".env.example").read_text(encoding="utf-8")


def test_the_key_patterns_catch_a_real_looking_key():
    fake = b'ANTHROPIC_API_KEY="sk-ant-api03-' + b"A" * 40 + b'"'
    assert any(pattern.search(fake) for pattern in KEY_LIKE)
    assert not any(
        pattern.search(b'monkeypatch.setenv("ANTHROPIC_API_KEY", "k")') for pattern in KEY_LIKE
    )


# ------------------------------------------------------------------ public models and the rules

PUBLIC_MODELS = sorted(p.stem for p in (ROOT / "dbt" / "models" / "marts").glob("rpt_public_*.sql"))


def test_every_public_model_is_covered_by_the_rules():
    """rpt_public_ghg_yoy included: listed in the safety test, the publication policy and the
    exports; its numeric columns are public_position rows of the KPI catalogue."""
    safety = (ROOT / "dbt" / "tests" / "assert_public_models_safe.sql").read_text(encoding="utf-8")
    policy = (ROOT / "docs" / "publication_policy.md").read_text(encoding="utf-8")
    assert "rpt_public_ghg_yoy" in PUBLIC_MODELS
    for model in PUBLIC_MODELS:
        assert f"ref('{model}')" in safety, f"{model} not in assert_public_models_safe"
        assert f"`{model}`" in policy, f"{model} not in publication_policy.md"


def test_rpt_public_ghg_yoy_has_only_computed_values():
    with (ROOT / "dbt" / "seeds" / "kpi_catalogue.csv").open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["source_model"] == "rpt_public_ghg_yoy"]
    names = {r["kpi_name"] for r in rows}
    assert names == {
        "intensity_from", "intensity_to", "change_pct", "n_companies_compared",
        "improvement_rank_in_group", "deterioration_rank_in_group",
        "improvement_rank_overall", "deterioration_rank_overall",
    }  # fmt: skip
    assert all(r["metric_type"] == "public_position" and r["public_safe"] == "true" for r in rows)
    sql = (ROOT / "dbt" / "models" / "marts" / "rpt_public_ghg_yoy.sql").read_text(encoding="utf-8")
    final_select = sql.rsplit("\nselect\n", 1)[1]
    for raw in ("ghg_s12_tco2e", "ghg_s1_tco2e", "ghg_s2_tco2e", "turnover_cr", "turnover_inr"):
        assert raw not in final_select, f"raw quantity {raw} in the output of rpt_public_ghg_yoy"


def test_check_public_catches_a_small_group_share(tmp_path):
    """The file check of exports/public flags a restatement share shown for fewer than 5 companies."""
    import shutil as _shutil
    import sys as _sys

    import pandas as pd

    public = ROOT / "exports" / "public"
    if not (public / "rpt_public_restatement_summary.parquet").exists():
        pytest.skip("run dev.ps1 bi-export first")
    _sys.path.insert(0, str(ROOT / "scripts"))
    import check_public

    for path in public.glob("rpt_public_*.parquet"):
        _shutil.copy(path, tmp_path / path.name)
    assert check_public.problems(tmp_path) == []
    frame = pd.read_parquet(tmp_path / "rpt_public_restatement_summary.parquet")
    small = (frame["level"] == "peer_group") & (frame["n_companies"] < 5)
    assert small.any()
    frame.loc[small, "pct_material"] = 12.3  # what the table published before the fix
    frame.to_parquet(tmp_path / "rpt_public_restatement_summary.parquet")
    found = check_public.problems(tmp_path)
    assert found and all("fewer than 5 companies" in p for p in found)
