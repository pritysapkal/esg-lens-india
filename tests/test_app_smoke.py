"""Smoke tests of the polished report card: every page loads with the AI analyst off, and the
headline numbers on screen match the public tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app import data

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app" / "streamlit_app.py"
PAGES = ["views/overview.py", "views/company.py", "views/sectors.py", "views/concentration.py",
         "views/ai_analyst.py", "views/methodology.py"]  # fmt: skip

pytestmark = pytest.mark.skipif(not data.available(), reason="run dev.ps1 bi-export first")


@pytest.fixture
def app(monkeypatch) -> AppTest:
    monkeypatch.delenv("ESG_AI_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    return at


def _metrics(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def test_every_page_loads_with_the_analyst_off(app):
    assert not app.exception
    for page in PAGES:
        app.switch_page(page).run()
        assert not app.exception, (page, app.exception)
        assert any("Data: NIFTY 50 + Wipro BRSR filings" in c.value for c in app.caption), page
        assert any(
            "Groups with fewer than 5 companies are suppressed" in c.value for c in app.caption
        ), page


def test_ai_analyst_is_off_by_default_and_labelled_experimental(app):
    app.switch_page("views/ai_analyst.py").run()
    assert not app.chat_input
    assert any("Experimental" in m.value for m in app.markdown)


def test_overview_top5_share_matches_the_public_table(app):
    conc = pd.read_parquet(data.PUBLIC_DIR / "rpt_public_concentration.parquet")
    row = conc[(conc["fiscal_year_label"] == "FY2025-26") & (conc["emitter_rank"] == 5)]
    expected = f"{row['cumulative_share_pct'].iloc[0]:.1f}%"
    assert expected == "85.5%"
    assert _metrics(app)["Emissions held by top 5 companies (%)"] == expected


def test_concentration_page_top5_matches(app):
    app.switch_page("views/concentration.py").run()
    assert _metrics(app)["Top 5 (% of total)"] == "85.5%"


def test_asset_heavy_aggregate_and_median_match_the_public_table(app):
    groups = pd.read_parquet(data.PUBLIC_DIR / "rpt_public_group_metrics.parquet")
    row = groups[
        (groups["group_type"] == "sector_group")
        & (groups["group_value"] == "Asset-heavy")
        & (groups["fiscal_year_label"] == "FY2025-26")
    ].iloc[0]
    assert f"{row['ghg_intensity_agg']:.2f}" == "248.81"
    assert f"{row['ghg_intensity_median']:.2f}" == "11.40"

    app.switch_page("views/sectors.py").run()
    assert app.dataframe[0].value.loc["Asset-heavy", "FY2025-26"] == "248.81"
    app.sidebar.selectbox[1].set_value("ghg_intensity_median").run()
    assert app.dataframe[0].value.loc["Asset-heavy", "FY2025-26"] == "11.40"


def test_company_page_shows_cards_for_a_company(app):
    app.switch_page("views/company.py").run()
    assert not app.exception
    labels = _metrics(app)
    assert "Score (0-100)" in labels and "Grade" in labels
