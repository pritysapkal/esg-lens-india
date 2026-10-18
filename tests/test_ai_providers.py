"""The local (Ollama) provider of the AI analyst, with a fake Ollama client: same tools, same
guardrails, same limits, same refusal behaviour as the Anthropic provider. No model and no network
are needed (runs in CI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import data  # noqa: E402
from app.ai_analyst import agent, providers, tools  # noqa: E402

pytestmark = pytest.mark.skipif(not data.available(), reason="run dev.ps1 bi-export first")


class FakeOllama:
    """Plays back scripted Ollama chat responses (plain dicts, as `ollama.Client.chat` returns
    objects with the same fields) and records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def chat(self, **request):
        self.requests.append(json.loads(json.dumps(request, default=str)))
        return self.responses.pop(0)


def _reply(content="", tool_calls=None, done_reason="stop"):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [{"function": {"name": n, "arguments": a}} for n, a in tool_calls]
    return {"model": "qwen2.5:3b", "message": message, "done_reason": done_reason,
            "prompt_eval_count": 900, "eval_count": 40, "total_duration": 2_000_000_000}  # fmt: skip


def ask(question, client, **kwargs):
    return agent.ask(question, client=client, provider="ollama", **kwargs)


def test_loop_runs_the_same_tools_and_returns_the_answer_with_its_calls():
    client = FakeOllama([
        _reply(tool_calls=[("concentration", {"year": "FY2024-25", "top_n": 5})]),
        _reply("The five largest emitters held 85.5% (concentration, rpt_public_concentration)."),
    ])  # fmt: skip
    answer = ask("How concentrated?", client)
    assert answer.provider == "ollama" and "85.5%" in answer.text
    assert [c.name for c in answer.calls] == ["concentration"]
    assert answer.calls[0].result["summary"]["top_5_share_pct"] == pytest.approx(85.4607, abs=1e-3)
    assert answer.input_tokens == 1800 and answer.output_tokens == 80

    first, second = client.requests
    # the same system prompt and the same six tools, in Ollama's function format
    assert first["messages"][0] == {"role": "system", "content": agent.SYSTEM_PROMPT}
    assert [t["function"]["name"] for t in first["tools"]] == [t.name for t in tools.tools()]
    assert first["tools"][0]["function"]["parameters"] == tools.tools()[0].schema()["input_schema"]
    # the limits: output cap, a fixed context window (Ollama's default would cut the prompt), no sampling noise
    assert first["options"] == {"num_predict": agent.LIMITS.max_output_tokens,
                                "num_ctx": agent.LIMITS.local_context_tokens, "temperature": 0}  # fmt: skip
    tool_message = second["messages"][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_name"] == "concentration"
    assert json.loads(tool_message["content"])["source"] == "rpt_public_concentration"


def test_bad_arguments_and_unknown_tools_go_back_as_errors():
    client = FakeOllama([
        _reply(tool_calls=[("company_card", {"company": "Tesla", "year": "FY2024-25"}),
                           ("run_sql", {"query": "select * from fct_company_year"})]),
        _reply("Tesla is not covered."),
    ])  # fmt: skip
    answer = ask("Tesla?", client)
    assert [c.error is not None for c in answer.calls] == [True, True]
    assert all(c.result is None for c in answer.calls)
    errors = [
        json.loads(m["content"])["error"]
        for m in client.requests[1]["messages"]
        if m["role"] == "tool"
    ]
    assert "not one of the" in errors[0] and "unknown tool" in errors[1]


def test_arguments_sent_as_a_json_string_are_parsed():
    client = FakeOllama([
        _reply(tool_calls=[("concentration", json.dumps({"year": "FY2024-25", "top_n": 3}))]),
        _reply("ok"),
    ])  # fmt: skip
    answer = ask("x", client)
    assert (
        answer.calls[0].arguments == {"year": "FY2024-25", "top_n": 3}
        and answer.calls[0].error is None
    )


def test_tool_calls_are_capped_and_then_tools_are_withdrawn():
    """Ollama has no tool_choice: past the limit the tools are simply not offered."""
    limit = agent.LIMITS.tool_calls_per_question
    client = FakeOllama(
        [_reply(tool_calls=[("concentration", {"year": "FY2024-25", "top_n": 3})]) for _ in range(limit)]
        + [_reply("Answer from what I have.")]
    )  # fmt: skip
    answer = ask("x", client)
    assert len(answer.calls) == limit and answer.text == "Answer from what I have."
    assert all("tools" in r for r in client.requests[:-1]) and "tools" not in client.requests[-1]
    assert len(client.requests) == agent.LIMITS.max_requests_per_question


def test_extra_calls_in_one_turn_are_not_run_and_a_runaway_model_is_cut_off():
    limit = agent.LIMITS.tool_calls_per_question
    many = [("concentration", {"year": "FY2024-25", "top_n": 3})] * (limit + 2)
    client = FakeOllama([_reply(tool_calls=many), _reply("ok")])
    answer = ask("x", client)
    assert len(answer.calls) == limit
    tool_messages = [m for m in client.requests[1]["messages"] if m["role"] == "tool"]
    assert sum("limit reached" in m["content"] for m in tool_messages) == 2

    endless = FakeOllama([_reply(tool_calls=[("concentration", {"year": "FY2024-25", "top_n": 3})])
                          for _ in range(agent.LIMITS.max_requests_per_question)])  # fmt: skip
    answer = ask("x", endless)
    assert (
        answer.stop_reason == "max_turns"
        and len(endless.requests) == agent.LIMITS.max_requests_per_question
    )


def test_out_of_scope_refusal_and_cut_off_answers():
    refused = ask(
        "Should I buy Reliance?",
        FakeOllama([_reply(agent.REFUSAL_PREFIX + ". I can tell you about intensities.")]),
    )
    assert (
        refused.refused and not refused.model_refused and not refused.calls
    )  # no retry, no other model
    cut = ask("x", FakeOllama([_reply("A long answer", done_reason="length")]))
    assert cut.stop_reason == "max_tokens" and "cut off" in cut.text


def test_question_limits_apply_before_anything_is_sent():
    client = FakeOllama([])
    with pytest.raises(agent.QuestionRejected):
        ask("x" * (agent.LIMITS.max_question_chars + 1), client)
    assert client.requests == []


def test_the_real_client_gets_the_local_host_and_the_timeout(monkeypatch):
    import ollama

    seen = {}
    monkeypatch.setattr(ollama, "Client", lambda **kwargs: seen.update(kwargs) or object())
    monkeypatch.setattr(agent, "setting", lambda name: None)
    agent.make_provider("ollama").client()
    assert seen == {"host": "http://127.0.0.1:11434", "timeout": agent.LIMITS.local_timeout_seconds}
    monkeypatch.setattr(agent, "setting", {"OLLAMA_HOST": "http://localhost:11500"}.get)
    agent.make_provider("ollama").client()
    assert seen["host"] == "http://localhost:11500"


def test_providers_read_no_file_and_hold_no_key():
    source = (ROOT / "app" / "ai_analyst" / "providers.py").read_text(encoding="utf-8")
    for forbidden in (
        "open(",
        "read_text",
        "dotenv",
        "os.environ",
        "fallbacks",
        "ANTHROPIC_API_KEY",
    ):
        assert forbidden not in source, forbidden
    assert providers.DEFAULT_MODELS == {"anthropic": "claude-haiku-4-5", "ollama": "qwen2.5:3b"}
