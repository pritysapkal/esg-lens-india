"""The AI analyst (Week 13): tool schemas, argument validation, tool results, the tool-use loop
(with a fake client - no API call), and the evaluation set. The live evaluation needs a key and
runs locally: .\\scripts\\dev.ps1 eval."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from app import data  # noqa: E402
from app.ai_analyst import agent, tools  # noqa: E402

pytestmark = pytest.mark.skipif(not data.available(), reason="run dev.ps1 bi-export first")
RAW_NAME = re.compile(
    r"(_tco2e|_gj|_kl)$|turnover|headcount|_num$|_den$|original_value|restated_value"
)


# ------------------------------------------------------------------ schemas and validation


def test_tool_set_is_fixed_and_schemas_are_strict():
    names = [t.name for t in tools.tools()]
    assert names == ["group_metric", "company_card", "company_percentiles", "concentration",
                     "top_movers_confirmed", "restatement_summary"]  # fmt: skip
    for tool in tools.tools():
        schema = tool.schema()
        assert schema["strict"] is True
        assert schema["input_schema"]["additionalProperties"] is False
        assert set(schema["input_schema"]["required"]) == set(schema["input_schema"]["properties"])
        assert "sql" not in json.dumps(schema).lower(), "no free-form SQL argument"
    json.dumps([t.schema() for t in tools.tools()])  # serialisable for the API


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        ("run_sql", {"query": "select * from fct_company_year"}, "unknown tool"),
        ("group_metric", {"metric": "ghg_s12_tco2e", "group_type": "all"}, "not allowed"),
        ("group_metric", {"metric": "ghg_intensity_agg", "group_type": "country"}, "not allowed"),
        (
            "group_metric",
            {
                "metric": "ghg_intensity_agg",
                "group_type": "sector_group",
                "group_value": "IT services",
            },
            "not allowed",
        ),
        (
            "group_metric",
            {"metric": "ghg_intensity_agg", "group_type": "all", "year": "FY2030-31"},
            "not allowed",
        ),
        (
            "group_metric",
            {"metric": "ghg_intensity_agg", "group_type": "all", "where": "1=1"},
            "does not take",
        ),
        ("company_card", {"company": "Tesla", "year": "FY2024-25"}, "not one of the"),
        ("company_card", {"company": "HDFC Bank", "year": 2024}, "not allowed"),
        ("concentration", {"year": "FY2024-25", "top_n": 500}, "whole number"),
        ("concentration", {"year": "FY2024-25", "top_n": True}, "whole number"),
        ("top_movers_confirmed", {"direction": "sideways"}, "not allowed"),
        ("restatement_summary", {"level": "everything"}, "not allowed"),
        (
            "company_percentiles",
            {"company": "Infosys", "year": "FY2024-25", "kpi": "ghg_scope1_tco2e"},
            "not allowed",
        ),
    ],
)
def test_bad_arguments_are_refused_before_any_query(name, arguments, message):
    with pytest.raises(tools.ToolArgumentError, match=message):
        tools.call(name, arguments)


def test_company_accepts_display_name_or_symbol():
    by_name = tools.call("company_card", {"company": "HDFC Bank", "year": "FY2024-25"})
    by_symbol = tools.call("company_card", {"company": "hdfcbank", "year": "FY2024-25"})
    assert by_name["card"] == by_symbol["card"]


# ------------------------------------------------------------------ results


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


EXAMPLES = [
    (
        "group_metric",
        {
            "metric": "ghg_intensity_median",
            "group_type": "ranking_group",
            "group_value": None,
            "year": None,
        },
    ),
    ("company_card", {"company": "Reliance", "year": "FY2025-26"}),
    ("company_percentiles", {"company": "Asian Paints", "year": "FY2024-25", "kpi": None}),
    ("concentration", {"year": "FY2025-26", "top_n": 20}),
    ("top_movers_confirmed", {"direction": "improvement", "ranking_group": None, "limit": 10}),
    ("restatement_summary", {"level": "company", "group_key": None}),
]


@pytest.mark.parametrize(("name", "arguments"), EXAMPLES, ids=[e[0] for e in EXAMPLES])
def test_tools_return_derived_values_only_with_a_source_and_notes(name, arguments):
    result = tools.call(name, arguments)
    assert result["source"].startswith("rpt_public_")
    assert isinstance(result["notes"], list)
    bad = {k for k in _keys(result) if RAW_NAME.search(k)}
    assert not bad, f"{name} returns raw-value keys {bad}"
    json.dumps(result)


def test_withheld_figures_come_back_as_withheld_not_as_numbers():
    result = tools.call("group_metric", {"metric": "ghg_intensity_median", "group_type": "ranking_group",
                                         "group_value": "Automobiles", "year": "FY2023-24"})  # fmt: skip
    (row,) = result["rows"]
    assert (
        row["value"] is None
        and row["status"] == "n<5 (withheld)"
        and row["companies_behind_it"] == 3
    )
    assert any("fewer than 5" in note for note in result["notes"])


def test_latest_year_comes_back_labelled_provisional():
    result = tools.call("concentration", {"year": data.latest_year(), "top_n": 5})
    assert any("provisional" in note for note in result["notes"])
    restated = tools.call("group_metric", {"metric": "material_restatement_share", "group_type": "all",
                                           "group_value": "All companies", "year": data.latest_year()})  # fmt: skip
    assert restated["rows"][0]["status"] == "not yet observable"


def test_top_movers_rank_only_confirmed_changes():
    result = tools.call(
        "top_movers_confirmed", {"direction": "improvement", "ranking_group": None, "limit": 10}
    )
    frame = data.table("rpt_public_ghg_yoy")
    ranked = frame[frame["is_ranked"].astype(bool)]
    assert result["ranked_pairs"] == len(ranked)
    assert {m["display_name"] for m in result["movers"]} <= set(ranked["display_name"])
    changes = [m["change_pct"] for m in result["movers"]]
    assert changes == sorted(changes)
    assert sum(result["pairs_not_ranked_by_reason"].values()) == len(frame) - len(ranked)


# ------------------------------------------------------------------ the loop (fake client)


class FakeClient:
    """Plays back scripted responses and records what the analyst sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.requests.append(json.loads(json.dumps(request, default=lambda o: o.__dict__)))
        return self.responses.pop(0)


def _response(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks), model="fake-model",
                           usage=SimpleNamespace(input_tokens=100, output_tokens=20))  # fmt: skip


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use(block_id, name, arguments):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=arguments)


def test_loop_runs_the_tools_and_returns_the_answer_with_its_calls():
    client = FakeClient([
        _response("tool_use", _text("Looking it up."), _tool_use("t1", "concentration", {"year": "FY2024-25", "top_n": 5})),
        _response("end_turn", _text("The five largest emitters held 85.5% (concentration, rpt_public_concentration).")),
    ])  # fmt: skip
    answer = agent.ask("How concentrated?", client=client, model="claude-opus-5-5")
    assert "85.5%" in answer.text
    assert [c.name for c in answer.calls] == ["concentration"]
    assert answer.calls[0].result["summary"]["top_5_share_pct"] == pytest.approx(85.4607, abs=1e-3)
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "t1"
    assert tool_result["is_error"] is False
    first = client.requests[0]
    assert first["system"] == agent.SYSTEM_PROMPT
    assert [t["name"] for t in first["tools"]] == [t.name for t in tools.tools()]
    assert first["fallbacks"] == "default" and first["betas"] == [agent.FALLBACK_BETA]
    assert answer.input_tokens == 200 and answer.output_tokens == 40


def test_bad_tool_arguments_go_back_to_the_model_as_an_error():
    client = FakeClient([
        _response("tool_use", _tool_use("t1", "company_card", {"company": "Tesla", "year": "FY2024-25"})),
        _response("end_turn", _text("Tesla is not covered.")),
    ])  # fmt: skip
    answer = agent.ask("Tesla?", client=client, model="claude-haiku-5-5")
    assert answer.calls[0].error and answer.calls[0].result is None
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True and "not one of the" in tool_result["content"]
    assert "fallbacks" not in client.requests[0]  # Haiku has no server-side fallback


def test_refusal_stop_reason_and_runaway_loops_are_handled():
    declined = agent.ask("x", client=FakeClient([_response("refusal")]), model="claude-opus-5-5")
    assert declined.stop_reason == "refusal" and "declined" in declined.text
    looping = FakeClient([_response("tool_use", _tool_use(f"t{i}", "concentration", {"year": "FY2024-25", "top_n": 3}))
                          for i in range(agent.MAX_TURNS)])  # fmt: skip
    answer = agent.ask("x", client=looping, model="claude-opus-5-5")
    assert answer.stop_reason == "max_turns" and len(answer.calls) == agent.MAX_TURNS


def test_out_of_scope_answer_counts_as_refused():
    client = FakeClient(
        [_response("end_turn", _text(agent.REFUSAL_PREFIX + ". I can tell you about intensities."))]
    )
    answer = agent.ask("Should I buy Reliance?", client=client, model="claude-opus-5-5")
    assert answer.refused and not answer.calls


def test_system_prompt_states_the_guardrails():
    prompt = agent.SYSTEM_PROMPT
    for phrase in ("tool result", "withheld", "provisional", "associations, never causes", agent.REFUSAL_PREFIX,
                   "not an ESG rating", "investment advice", "Do not build group figures"):  # fmt: skip
        assert phrase in prompt, phrase


def test_disabled_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert agent.is_enabled() is False
    monkeypatch.setenv("ESG_AI_MODEL", "claude-sonnet-5-5")
    assert agent.model_name() == "claude-sonnet-5-5"


# ------------------------------------------------------------------ the evaluation set


def test_evaluation_set_has_the_required_mix():
    import eval_ai_analyst

    questions = eval_ai_analyst.load()
    assert len(questions) == 20 and len({q["id"] for q in questions}) == 20
    counts = {
        c: sum(q["category"] == c for q in questions)
        for c in ("refusal", "suppressed", "provisional")
    }
    assert counts["refusal"] >= 3 and counts["suppressed"] >= 3 and counts["provisional"] >= 2
    for q in questions:
        assert set(q["expected_tools"]) == {c["tool"] for c in q["expected_calls"]}, q["id"]


def test_evaluation_answers_are_what_the_tools_return_today():
    import eval_ai_analyst

    problems = {q["id"]: eval_ai_analyst.check_offline(q) for q in eval_ai_analyst.load()}
    assert not {k: v for k, v in problems.items() if v}


def test_scoring_rules():
    import eval_ai_analyst

    question = {
        "id": "x",
        "category": "suppressed",
        "expected_tools": ["group_metric"],
        "expected_numbers": [],
    }
    good = agent.Answer(
        text="It is withheld: fewer than 5 companies.", calls=[agent.ToolCall("group_metric", {})]
    )
    assert eval_ai_analyst.score(question, good)["passed"]
    causal = agent.Answer(
        text="Withheld; low disclosure leads to high emissions.", calls=good.calls
    )
    assert not eval_ai_analyst.score(question, causal)["passed"]
    number_q = {
        "id": "y",
        "category": "normal",
        "expected_tools": [],
        "expected_numbers": [{"value": -40.3, "tolerance": 0.1, "absolute": True}],
    }
    assert eval_ai_analyst.score(number_q, agent.Answer(text="It fell by 40.3%."))["numbers"]
    assert not eval_ai_analyst.score(number_q, agent.Answer(text="It fell by 4.3%."))["numbers"]
