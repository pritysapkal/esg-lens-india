"""The "Numbers used" panel of an AI answer and the guided-question tables: every tool's output and
every guided question type renders without an exception and with unique, reader-facing headers.
A duplicate header (two raw columns with the same label) once broke the AI answer page."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import answer_view, data, guided, labels  # noqa: E402
from app.ai_analyst import agent, tools  # noqa: E402

needs_public = pytest.mark.skipif(not data.available(), reason="run dev.ps1 bi-export first")

# Sample calls of every tool, with and without the optional arguments, as the model makes them.
TOOL_SAMPLES = [
    ("group_metric", {"metric": "ghg_intensity_median", "group_type": "ranking_group",
                      "group_value": None, "year": None}),
    ("group_metric", {"metric": "ghg_intensity_agg", "group_type": "sector_group",
                      "group_value": "Asset-heavy", "year": "FY2024-25"}),
    ("group_metric", {"metric": "material_restatement_share", "group_type": "all",
                      "group_value": "All companies", "year": None}),
    ("company_card", {"company": "HDFC Bank", "year": "FY2024-25"}),
    ("company_card", {"company": "Reliance", "year": "FY2025-26"}),
    ("company_percentiles", {"company": "Asian Paints", "year": "FY2024-25",
                             "kpi": "ghg_intensity_tco2e_per_cr"}),
    ("company_percentiles", {"company": "Asian Paints", "year": "FY2024-25", "kpi": None}),
    ("concentration", {"year": "FY2024-25", "top_n": 5}),
    ("concentration", {"year": "FY2025-26", "top_n": 20}),
    ("top_movers_confirmed", {"direction": "improvement", "ranking_group": None, "limit": 10}),
    ("top_movers_confirmed", {"direction": "deterioration", "ranking_group": "Asset-heavy",
                              "limit": 3}),
    ("top_movers_confirmed", {"direction": "improvement", "ranking_group": "Financials",
                              "limit": 3}),
    ("restatement_summary", {"level": "overall", "group_key": None}),
    ("restatement_summary", {"level": "peer_group", "group_key": None}),
    ("restatement_summary", {"level": "metric", "group_key": None}),
    ("restatement_summary", {"level": "company", "group_key": None}),
]  # fmt: skip


@pytest.fixture
def shown(monkeypatch):
    """Every frame passed to st.dataframe (which still runs, so its own checks apply too)."""
    frames: list[pd.DataFrame] = []
    real = st.dataframe

    def recording(frame, *args, **kwargs):
        frames.append(frame)
        return real(frame, *args, **kwargs)

    monkeypatch.setattr(st, "dataframe", recording)
    return frames


def _check_headers(frames: list[pd.DataFrame], where: str) -> None:
    for frame in frames:
        headers = [str(c) for c in frame.columns]
        duplicates = sorted({h for h in headers if headers.count(h) > 1})
        assert not duplicates, f"{where}: duplicate headers {duplicates}"
        raw = [h for h in headers if "_" in h]
        assert not raw, f"{where}: raw column names {raw}"


def test_every_tool_is_sampled():
    assert {name for name, _ in TOOL_SAMPLES} == set(tools.by_name())
    assert {name for name, _ in TOOL_SAMPLES} == {q.tool for q in guided.QUESTION_TYPES}


@needs_public
@pytest.mark.parametrize(
    ("name", "arguments"), TOOL_SAMPLES, ids=[f"{n}-{i}" for i, (n, _) in enumerate(TOOL_SAMPLES)]
)
def test_numbers_used_panel_renders_every_tool(shown, name, arguments):
    call = agent.ToolCall(name, arguments, result=tools.call(name, arguments))
    answer_view.show_calls([call])
    _check_headers(shown, f"{name}{arguments}")
    assert len(shown) == len(answer_view.call_tables(call.result))


@needs_public
def test_numbers_used_panel_renders_all_calls_of_one_answer(shown):
    """The crash that started this: GHG ranking question, the company_percentiles call."""
    calls = [agent.ToolCall(n, a, result=tools.call(n, a)) for n, a in TOOL_SAMPLES]
    calls.append(agent.ToolCall("concentration", {"year": "FY1999-00"}, error="year not allowed"))
    answer_view.show_calls(calls)
    assert shown
    _check_headers(shown, "all calls")


def _guided_picks() -> list[tuple[str, dict]]:
    o = guided.choices()
    final = o["years"][-2]
    company = "Asian Paints"
    picks = [
        ("group", {"metric": "ghg_intensity_agg", "group_type": "sector_group",
                   "group_value": "Asset-heavy", "year": final}),
        ("group", {"metric": "dqs_median", "group_type": "ranking_group",
                   "group_value": "Automobiles", "year": guided.ALL_YEARS}),
        ("concentration", {"year": final, "top_n": 10}),
        ("concentration", {"year": o["years"][-1], "top_n": 3}),
    ]  # fmt: skip
    for year in o["years"]:
        picks.append(("card", {"company": company, "year": year}))
        picks.append(("peers", {"company": company, "year": year, "kpi": guided.ALL_KPIS}))
    picks += [("peers", {"company": company, "year": final, "kpi": k}) for k in o["kpis"]]
    for direction in ("improvement", "deterioration"):
        for group in ["All ranking groups", *o["ranking_groups"]]:
            picks.append(("movers", {"direction": direction, "ranking_group": group, "limit": 5}))
    picks += [("restatements", {"level": level}) for level in o["restatement_levels"]]
    return picks


@needs_public
def test_every_guided_question_renders_with_unique_headers(shown):
    picks = _guided_picks()
    assert {key for key, _ in picks} == set(guided.BY_KEY)
    for key, pick in picks:
        before = len(shown)
        answer = guided.ask(key, pick)
        answer_view.show_table(answer.table)
        answer_view.show_notes(answer.notes)
        if not answer.table.empty:
            _check_headers(shown[before:], f"guided {key} {pick}")


# ------------------------------------------------------------------ labels.friendly


def test_friendly_labels_are_unique_for_every_tool_output_column():
    """Within one tool's output no two columns share a label (kpi and kpi_label once did)."""
    pairs = [("kpi", "kpi_label"), ("percentile_in_group", "rank_in_group")]
    for columns in pairs:
        frame = labels.friendly(pd.DataFrame(columns=list(columns)))
        assert len(set(frame.columns)) == len(columns)
    assert labels.FRIENDLY_COLUMNS["kpi"] != labels.FRIENDLY_COLUMNS["kpi_label"]


def test_friendly_raises_on_a_clash_in_tests_and_tells_columns_apart_on_the_site():
    clash = pd.DataFrame({"group": ["a"], "group_value": ["b"]})
    with pytest.raises(ValueError, match="same label"):
        labels.friendly(clash)  # under pytest: strict
    with pytest.raises(ValueError, match="same label"):
        labels.friendly(clash, strict=True)
    relaxed = labels.friendly(clash, strict=False)
    assert list(relaxed.columns) == ["Group (group)", "Group (group value)"]
    assert list(clash.columns) == ["group", "group_value"]  # the input is left as it was
