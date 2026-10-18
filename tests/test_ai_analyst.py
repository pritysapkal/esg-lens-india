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
        self.messages = SimpleNamespace(create=self._create)
        # the analyst uses the plain Messages API; a beta call fails the test
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._no_beta))

    def _no_beta(self, **request):
        raise AssertionError("the analyst must not use the beta endpoint")

    def _create(self, **request):
        self.requests.append(json.loads(json.dumps(request, default=lambda o: o.__dict__)))
        return self.responses.pop(0)


def _response(stop_reason, *blocks, stop_details=None):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks), model="fake-model", stop_details=stop_details,
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
    answer = agent.ask("How concentrated?", client=client, model="claude-haiku-4-5")
    assert "85.5%" in answer.text
    assert [c.name for c in answer.calls] == ["concentration"]
    assert answer.calls[0].result["summary"]["top_5_share_pct"] == pytest.approx(85.4607, abs=1e-3)
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "t1"
    assert tool_result["is_error"] is False
    first = client.requests[0]
    assert first["system"] == agent.SYSTEM_PROMPT
    assert [t["name"] for t in first["tools"]] == [t.name for t in tools.tools()]
    # no refusal fallback, no beta, no effort for claude-haiku-4-5, the output cap on every request
    for request in client.requests:
        assert not {"fallbacks", "betas", "output_config"} & set(request)
        assert request["max_tokens"] == agent.LIMITS.max_output_tokens
        assert "tool_choice" not in request
    assert answer.input_tokens == 200 and answer.output_tokens == 40


def test_bad_tool_arguments_go_back_to_the_model_as_an_error():
    client = FakeClient([
        _response("tool_use", _tool_use("t1", "company_card", {"company": "Tesla", "year": "FY2024-25"})),
        _response("end_turn", _text("Tesla is not covered.")),
    ])  # fmt: skip
    answer = agent.ask("Tesla?", client=client, model="claude-haiku-4-5")
    assert answer.calls[0].error and answer.calls[0].result is None
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True and "not one of the" in tool_result["content"]


def test_a_refusal_stays_a_refusal_and_is_shown():
    """No retry on another model: one request, and the refusal goes back to the user as such."""
    client = FakeClient([_response("refusal", stop_details=SimpleNamespace(category="cyber"))])
    declined = agent.ask("x", client=client, model="claude-haiku-4-5")
    assert len(client.requests) == 1 and not client.responses
    assert declined.model_refused and declined.refused and declined.refusal_category == "cyber"
    assert "declined" in declined.text and not declined.calls


def test_tool_calls_are_capped_per_question():
    """The model asks for a tool on every turn: only LIMITS.tool_calls_per_question run, and the
    last request forbids tools so the model has to answer."""
    limit = agent.LIMITS.tool_calls_per_question
    looping = FakeClient(
        [_response("tool_use", _tool_use(f"t{i}", "concentration", {"year": "FY2024-25", "top_n": 3})) for i in range(limit)]
        + [_response("end_turn", _text("Answer from what I have."))]
    )  # fmt: skip
    answer = agent.ask("x", client=looping, model="claude-haiku-4-5")
    assert len(answer.calls) == limit and answer.text == "Answer from what I have."
    assert len(looping.requests) == agent.LIMITS.max_requests_per_question
    assert looping.requests[-1]["tool_choice"] == {"type": "none"}
    assert all("tool_choice" not in r for r in looping.requests[:-1])


def test_extra_tool_calls_in_one_turn_are_not_run():
    limit = agent.LIMITS.tool_calls_per_question
    many = [
        _tool_use(f"t{i}", "concentration", {"year": "FY2024-25", "top_n": 3})
        for i in range(limit + 3)
    ]
    client = FakeClient([_response("tool_use", *many), _response("end_turn", _text("ok"))])
    answer = agent.ask("x", client=client, model="claude-haiku-4-5")
    assert len(answer.calls) == limit
    results = client.requests[1]["messages"][-1]["content"]
    assert len(results) == limit + 3 and sum(r["is_error"] for r in results) == 3
    assert all("limit reached" in r["content"] for r in results[limit:])
    assert client.requests[1]["tool_choice"] == {"type": "none"}


def test_a_model_that_never_stops_is_cut_off():
    client = FakeClient([_response("tool_use", _tool_use(f"t{i}", "concentration", {"year": "FY2024-25", "top_n": 3}))
                         for i in range(agent.LIMITS.max_requests_per_question)])  # fmt: skip
    answer = agent.ask("x", client=client, model="claude-haiku-4-5")
    assert answer.stop_reason == "max_turns"
    assert len(client.requests) == agent.LIMITS.max_requests_per_question


def test_question_limits_per_session_and_length():
    limits = agent.LIMITS
    assert limits.questions_per_session == 10 and limits.tool_calls_per_question == 4
    assert limits.max_output_tokens <= 2000 and limits.timeout_seconds <= 60
    assert limits.max_retries <= 1
    assert agent.check_question("  What is the top-5 share?  ", 9) == "What is the top-5 share?"
    with pytest.raises(agent.QuestionRejected, match="10 questions"):
        agent.check_question("again", limits.questions_per_session)
    with pytest.raises(agent.QuestionRejected, match="characters"):
        agent.check_question("x" * (limits.max_question_chars + 1))
    with pytest.raises(agent.QuestionRejected):
        agent.ask("x" * (limits.max_question_chars + 1), client=FakeClient([]))


def test_client_gets_the_key_timeout_and_retries_explicitly(monkeypatch):
    import anthropic

    seen = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: seen.update(kwargs) or object())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-from-env")
    agent._client()
    assert seen == {"api_key": "test-key-from-env", "timeout": agent.LIMITS.timeout_seconds,
                    "max_retries": agent.LIMITS.max_retries}  # fmt: skip


def test_out_of_scope_answer_counts_as_refused():
    client = FakeClient(
        [_response("end_turn", _text(agent.REFUSAL_PREFIX + ". I can tell you about intensities."))]
    )
    answer = agent.ask("Should I buy Reliance?", client=client, model="claude-haiku-4-5")
    assert answer.refused and not answer.calls


def test_system_prompt_states_the_guardrails():
    prompt = agent.SYSTEM_PROMPT
    for phrase in ("tool result", "withheld", "provisional", "associations, never causes", agent.REFUSAL_PREFIX,
                   "not an ESG rating", "investment advice", "Do not build group figures"):  # fmt: skip
        assert phrase in prompt, phrase


@pytest.mark.parametrize(
    ("switch", "key", "enabled"),
    [(None, None, False), ("true", None, False), (None, "k", False), ("false", "k", False),
     ("yes", "k", False), ("true", "k", True), ("TRUE", "k", True)],
)  # fmt: skip
def test_off_unless_the_switch_and_a_key_are_both_set(monkeypatch, switch, key, enabled):
    values = {"ESG_AI_ENABLED": switch, "ANTHROPIC_API_KEY": key}
    monkeypatch.setattr(agent, "setting", values.get)
    assert agent.is_enabled() is enabled
    if not enabled:
        assert agent.disabled_reason()


def test_settings_come_only_from_the_environment_or_streamlit_secrets(monkeypatch):
    import streamlit as st

    monkeypatch.delenv("ESG_AI_ENABLED", raising=False)
    monkeypatch.setattr(st, "secrets", {"ESG_AI_ENABLED": "true"})
    assert agent.setting("ESG_AI_ENABLED") == "true"  # from st.secrets
    monkeypatch.setenv("ESG_AI_ENABLED", "false")
    assert agent.setting("ESG_AI_ENABLED") == "false"  # the environment wins
    monkeypatch.setattr(st, "secrets", {})
    monkeypatch.delenv("ESG_AI_ENABLED")
    assert agent.setting("ESG_AI_ENABLED") is None
    # nothing else is read: no dotenv, no file, no credential profile
    source = (ROOT / "app" / "ai_analyst" / "agent.py").read_text(encoding="utf-8")
    for forbidden in ("dotenv", "open(", "read_text", "auth_token", "ANTHROPIC_PROFILE"):
        assert forbidden not in source, forbidden


def test_default_model_and_override(monkeypatch):
    monkeypatch.setattr(agent, "setting", lambda name: None)
    assert agent.DEFAULT_MODEL == "claude-haiku-4-5" and agent.model_name() == "claude-haiku-4-5"
    monkeypatch.setattr(agent, "setting", {"ESG_AI_MODEL": "claude-sonnet-5-5"}.get)
    assert agent.model_name() == "claude-sonnet-5-5"


def test_no_refusal_fallback_anywhere_in_the_analyst():
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "fallbacks" not in text and "server-side-fallback" not in text, path


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
