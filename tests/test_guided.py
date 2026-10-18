"""Guided questions (no language model): every question type runs through the validated AI-analyst
tools and nothing else, offers only values the tools accept, and answers with a sentence, a table
with reader-facing column names, and the withheld / provisional notes."""

from __future__ import annotations

import ast
import itertools
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import data, guided, labels  # noqa: E402
from app.ai_analyst import tools  # noqa: E402

pytestmark = pytest.mark.skipif(not data.available(), reason="run dev.ps1 bi-export first")

EXAMPLES = {
    "group": {
        "metric": "ghg_intensity_agg",
        "group_type": "sector_group",
        "group_value": "Asset-heavy",
        "year": "FY2024-25",
    },
    "card": {"company": "HDFC Bank", "year": "FY2024-25"},
    "peers": {"company": "Asian Paints", "year": "FY2024-25", "kpi": "ghg_intensity_tco2e_per_cr"},
    "concentration": {"year": "FY2024-25", "top_n": 5},
    "movers": {"direction": "improvement", "ranking_group": "All ranking groups", "limit": 3},
    "restatements": {"level": "overall"},
}


@pytest.fixture
def spy(monkeypatch):
    """Records every tool call the guided mode makes (and still runs the real tool)."""
    calls = []
    real = tools.call

    def recording(name, arguments):
        calls.append((name, dict(arguments)))
        return real(name, arguments)

    monkeypatch.setattr(tools, "call", recording)
    return calls


def test_one_question_type_per_tool():
    assert sorted(q.tool for q in guided.QUESTION_TYPES) == sorted(t.name for t in tools.tools())
    assert set(EXAMPLES) == set(guided.BY_KEY)


@pytest.mark.parametrize("key", list(EXAMPLES))
def test_every_question_runs_through_the_validated_tool(key, spy):
    answer = guided.ask(key, EXAMPLES[key])
    assert spy == [(guided.BY_KEY[key].tool, answer.arguments)]
    assert answer.tool == guided.BY_KEY[key].tool and answer.call_text.startswith(answer.tool + "(")
    assert answer.sentence and answer.source.startswith("rpt_public_")
    assert not answer.table.empty
    raw = [c for c in answer.table.columns if "_" in str(c)]
    assert not raw, f"raw column names shown: {raw}"


def test_guided_module_has_no_other_query_path():
    """Static check: guided.py imports no data access, reads no file, runs no SQL; its only door to
    the data is tools.call (and tools.allowed for the dropdown values)."""
    source = (ROOT / "app" / "guided.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "data" not in imported and "duckdb" not in imported
    for forbidden in ("read_parquet", "open(", "duckdb", "select ", "data.table", ".query("):
        assert forbidden not in source, forbidden
    used = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "tools"
    }
    assert used <= {"call", "allowed"}, used


def test_dropdowns_offer_exactly_what_the_tools_accept():
    choices, allowed = guided.choices(), tools.allowed()
    for key in ("years", "companies", "metrics", "group_types", "ranking_groups"):
        assert choices[key] == allowed[key], key
    assert sorted(choices["kpis"]) == sorted(allowed["kpis"])
    assert set(choices["restatement_levels"]) <= set(allowed["restatement_levels"])
    for group_type in allowed["group_types"]:
        assert guided.group_values(group_type), group_type


def test_a_value_the_tools_do_not_accept_is_refused():
    with pytest.raises(tools.ToolArgumentError):
        guided.ask("card", {"company": "Tesla", "year": "FY2024-25"})
    with pytest.raises(tools.ToolArgumentError):
        guided.ask("group", {**EXAMPLES["group"], "metric": "ghg_intensity_num"})  # a hidden sum


def test_withheld_figures_are_said_to_be_withheld():
    answer = guided.ask("group", {"metric": "ghg_intensity_median", "group_type": "ranking_group",
                                  "group_value": "Automobiles", "year": "FY2023-24"})  # fmt: skip
    assert "withheld" in answer.sentence and "3 companies" in answer.sentence
    assert any("n<5" in note for note in answer.notes)
    assert "n<5 (withheld)" in answer.table.iloc[0].tolist()


def test_provisional_year_carries_its_note():
    answer = guided.ask("concentration", {"year": "FY2025-26", "top_n": 5})
    assert any("provisional" in note for note in answer.notes)
    assert "85.5%" in answer.sentence


def test_not_ranked_kpi_says_why():
    answer = guided.ask(
        "peers", {"company": "Infosys", "year": "FY2025-26", "kpi": "water_intensity_kl_per_cr"}
    )
    assert "not material" in answer.sentence


def test_restatement_shares_follow_the_five_company_rule():
    """rpt_public_restatement_summary has peer groups of 3 or 4 companies; guided mode withholds
    their shares the way every other group statistic is withheld."""
    answer = guided.ask("restatements", {"level": "peer_group"})
    table = answer.table
    small = table[table["Companies"] < 5]
    assert not small.empty
    assert (small["Restated materially (%)"] == "n<5 (withheld)").all()
    assert (table[table["Companies"] >= 5]["Restated materially (%)"] != "n<5 (withheld)").all()


def test_numbers_in_the_sentence_match_the_tool_result():
    answer = guided.ask("card", EXAMPLES["card"])
    card = tools.call("company_card", EXAMPLES["card"])["card"]
    assert f"{card['dqs_total']:.1f} of 100" in answer.sentence
    assert f"rank {card['dqs_rank_in_group']:.0f} of {card['dqs_group_n']:.0f}" in answer.sentence


def test_every_combination_of_group_question_runs():
    """All group types x every group x every metric for one year: no error, no raw names."""
    choices = guided.choices()
    for group_type, metric in itertools.product(choices["group_types"], choices["metrics"]):
        for group_value in guided.group_values(group_type):
            answer = guided.ask("group", {"metric": metric, "group_type": group_type,
                                          "group_value": group_value, "year": "FY2024-25"})  # fmt: skip
            assert answer.sentence
            assert not [c for c in answer.table.columns if "_" in str(c)]


def test_kpi_pillars_cover_every_public_kpi():
    kpis = set(data.table("rpt_public_company_percentile")["kpi_name"])
    assert kpis == set(labels.KPI_INFO)
    assert {pillar for _, pillar in labels.KPI_INFO.values()} == set(labels.PILLARS)
