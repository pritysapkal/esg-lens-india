"""The local (Ollama) and Gemini providers of the AI analyst, with fake clients: same tools, same
guardrails, same limits, same refusal behaviour as the Anthropic provider; for Gemini also the
free-tier failures (quota, key, API error) raised as ProviderUnavailable. No model and no network
are needed (runs in CI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

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
        "os.getenv",
        "fallbacks",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        assert forbidden not in source, forbidden
    assert providers.DEFAULT_MODELS == {"anthropic": "claude-haiku-4-5", "ollama": "qwen2.5:3b",
                                        "gemini": "gemini-3.5-flash-lite"}  # fmt: skip


# ------------------------------------------------------------------ Gemini (fake client)


class FakeGemini:
    """Plays back scripted Gemini responses (plain dicts with the fields of the SDK's
    GenerateContentResponse) or raises scripted errors, and records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **request):
        self.requests.append(json.loads(json.dumps(request, default=str)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _gemini(text="", calls=(), finish="STOP", block=None, with_ids=True):
    parts = [{"text": text}] if text else []
    parts += [
        {"function_call": {"name": n, "args": a, **({"id": f"fc{i}"} if with_ids else {})}}
        for i, (n, a) in enumerate(calls)
    ]
    candidate = {"content": {"role": "model", "parts": parts}, "finish_reason": finish}
    return {
        "model_version": "gemini-3.5-flash-lite",
        "candidates": [] if block else [candidate],
        "prompt_feedback": {"block_reason": block} if block else None,
        "usage_metadata": {"prompt_token_count": 800, "candidates_token_count": 30},
    }


def ask_gemini(question, client, **kwargs):
    return agent.ask(question, client=client, provider="gemini", **kwargs)


CONCENTRATION = ("concentration", {"year": "FY2024-25", "top_n": 3})


def test_gemini_loop_runs_the_same_tools_with_the_same_limits():
    from google.genai import types

    client = FakeGemini([
        _gemini(calls=[("concentration", {"year": "FY2024-25", "top_n": 5})]),
        _gemini("The five largest emitters held 85.5% (concentration, rpt_public_concentration)."),
    ])  # fmt: skip
    answer = ask_gemini("How concentrated?", client)
    assert answer.provider == "gemini" and "85.5%" in answer.text
    assert [c.name for c in answer.calls] == ["concentration"]
    assert answer.calls[0].result["summary"]["top_5_share_pct"] == pytest.approx(85.4607, abs=1e-3)
    assert answer.input_tokens == 1600 and answer.output_tokens == 60

    first, second = client.requests
    config = first["config"]
    assert first["model"] == "gemini-3.5-flash-lite"
    assert config["system_instruction"] == agent.SYSTEM_PROMPT
    declarations = config["tools"][0]["function_declarations"]
    assert [d["name"] for d in declarations] == [t.name for t in tools.tools()]
    assert declarations[0]["parameters_json_schema"] == tools.tools()[0].schema()["input_schema"]
    assert config["max_output_tokens"] == agent.LIMITS.max_output_tokens
    assert config["temperature"] == 0
    assert config["automatic_function_calling"] == {"disable": True}  # our loop runs the tools
    assert config["tool_config"] == {"function_calling_config": {"mode": "AUTO"}}
    (response_part,) = second["contents"][-1]["parts"]
    function_response = response_part["function_response"]
    assert function_response["name"] == "concentration" and function_response["id"] == "fc0"
    assert function_response["response"]["output"]["source"] == "rpt_public_concentration"
    # what is sent is valid for the real SDK types (no network)
    types.GenerateContentConfig.model_validate(config)
    for content in second["contents"]:
        types.Content.model_validate(content)


def test_gemini_bad_arguments_and_unknown_tools_go_back_as_errors():
    client = FakeGemini([
        _gemini(calls=[("company_card", {"company": "Tesla", "year": "FY2024-25"}),
                       ("run_sql", {"query": "select * from fct_company_year"})], with_ids=False),
        _gemini("Tesla is not covered."),
    ])  # fmt: skip
    answer = ask_gemini("Tesla?", client)
    assert [c.error is not None for c in answer.calls] == [True, True]
    assert all(c.result is None for c in answer.calls)
    parts = client.requests[1]["contents"][-1]["parts"]
    errors = [p["function_response"]["response"]["error"] for p in parts]
    assert "not one of the" in errors[0] and "unknown tool" in errors[1]
    assert all("id" not in p["function_response"] for p in parts)  # no id was given, none made up


def test_gemini_tool_calls_are_capped_and_then_forbidden():
    limit = agent.LIMITS.tool_calls_per_question
    client = FakeGemini(
        [_gemini(calls=[CONCENTRATION]) for _ in range(limit)]
        + [_gemini("Answer from what I have.")]
    )
    answer = ask_gemini("x", client)
    assert len(answer.calls) == limit and answer.text == "Answer from what I have."
    assert len(client.requests) == agent.LIMITS.max_requests_per_question
    modes = [r["config"]["tool_config"]["function_calling_config"]["mode"] for r in client.requests]
    assert modes == ["AUTO"] * limit + ["NONE"]


def test_gemini_extra_calls_are_not_run_and_a_runaway_model_is_cut_off():
    limit = agent.LIMITS.tool_calls_per_question
    client = FakeGemini([_gemini(calls=[CONCENTRATION] * (limit + 2)), _gemini("ok")])
    answer = ask_gemini("x", client)
    assert len(answer.calls) == limit
    parts = client.requests[1]["contents"][-1]["parts"]
    assert sum("limit reached" in json.dumps(p) for p in parts) == 2

    endless = FakeGemini(
        [_gemini(calls=[CONCENTRATION]) for _ in range(agent.LIMITS.max_requests_per_question)]
    )
    answer = ask_gemini("x", endless)
    assert answer.stop_reason == "max_turns"
    assert len(endless.requests) == agent.LIMITS.max_requests_per_question


@pytest.mark.parametrize(
    ("response", "category"),
    [(_gemini(finish="SAFETY"), "safety"), (_gemini(finish="PROHIBITED_CONTENT"), "prohibited_content"),
     (_gemini(block="JAILBREAK"), "jailbreak")],
)  # fmt: skip
def test_gemini_refusal_stays_a_refusal(response, category):
    """A safety stop of Gemini (answer or question blocked): one request, shown as a refusal,
    never retried on another model or provider."""
    client = FakeGemini([response])
    declined = ask_gemini("x", client)
    assert len(client.requests) == 1 and not client.responses
    assert declined.model_refused and declined.refused and declined.refusal_category == category
    assert "declined" in declined.text and not declined.calls


def test_gemini_out_of_scope_refusal_and_cut_off_answer():
    refused = ask_gemini(
        "Should I buy Reliance?",
        FakeGemini([_gemini(agent.REFUSAL_PREFIX + ". I can tell you about intensities.")]),
    )
    assert refused.refused and not refused.model_refused and not refused.calls
    cut = ask_gemini("x", FakeGemini([_gemini("A long answer", finish="MAX_TOKENS")]))
    assert cut.stop_reason == "max_tokens" and "cut off" in cut.text


def api_error(code, status):
    """An error as the Gemini SDK raises it (google.genai.errors)."""
    from google.genai import errors

    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": "fake", "status": status}})


@pytest.fixture
def no_backoff(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(agent, "LIMITS", replace(agent.LIMITS, retry_backoff_seconds=0))


@pytest.mark.parametrize(
    ("error", "reason", "transient"),
    [(lambda: api_error(429, "RESOURCE_EXHAUSTED"), "quota", False),
     (lambda: api_error(400, "API_KEY_INVALID"), "auth", False),
     (lambda: api_error(403, "PERMISSION_DENIED"), "auth", False),
     (lambda: api_error(400, "INVALID_ARGUMENT"), "error", False),
     (lambda: api_error(503, "UNAVAILABLE"), "error", True),
     (lambda: api_error(504, "DEADLINE_EXCEEDED"), "error", True),
     (lambda: TimeoutError("read timed out"), "error", True)],
)  # fmt: skip
def test_gemini_quota_key_and_api_errors_become_provider_unavailable(
    no_backoff, error, reason, transient
):
    """The page turns these into a plain message and the guided questions (tests/test_app.py).
    Only a server error or a timeout is retried, once; never a quota, key or request error."""
    client = FakeGemini([_gemini(calls=[CONCENTRATION]), error(), error()])
    with pytest.raises(agent.ProviderUnavailable) as raised:
        ask_gemini("x", client)
    assert raised.value.reason == reason and raised.value.transient == transient
    assert len(client.requests) == (3 if transient else 2)  # never another model or provider


def test_a_504_is_retried_once_after_a_wait_and_the_answer_comes_through(monkeypatch):
    waits = []
    monkeypatch.setattr(agent.time, "sleep", waits.append)
    client = FakeGemini([
        api_error(504, "DEADLINE_EXCEEDED"),
        _gemini(calls=[CONCENTRATION]),
        TimeoutError("read timed out"),
        _gemini("The three largest emitters held most of it."),
    ])  # fmt: skip
    answer = ask_gemini("How concentrated?", client)
    assert answer.text.startswith("The three largest") and len(client.requests) == 4
    assert waits == [agent.LIMITS.retry_backoff_seconds] * 2  # each request: one retry, one wait


def test_quota_and_refusals_are_never_retried(no_backoff):
    client = FakeGemini([api_error(429, "RESOURCE_EXHAUSTED"), _gemini("never sent")])
    with pytest.raises(agent.ProviderUnavailable):
        ask_gemini("x", client)
    assert len(client.requests) == 1
    client = FakeGemini([_gemini(finish="SAFETY"), _gemini("never sent")])
    assert ask_gemini("x", client).model_refused and len(client.requests) == 1


def test_transient_errors_of_every_provider():
    """5xx and timeouts of the Anthropic and Ollama SDKs count too; 429 and 4xx never do."""
    import anthropic
    import httpx

    request = httpx.Request("POST", "https://example.invalid")

    def status(cls, code):
        return cls("x", response=httpx.Response(code, request=request), body=None)

    assert providers.is_transient(status(anthropic.InternalServerError, 529))
    assert providers.is_transient(anthropic.APITimeoutError(request=request))
    assert providers.is_transient(httpx.ReadTimeout("slow"))
    assert not providers.is_transient(status(anthropic.RateLimitError, 429))
    assert not providers.is_transient(status(anthropic.BadRequestError, 400))
    assert not providers.is_transient(ValueError("bad"))
    import ollama

    assert providers.is_transient(ollama.ResponseError("busy", 503))
    assert not providers.is_transient(ollama.ResponseError("no model", 404))


def test_gemini_client_gets_the_key_timeout_and_no_quota_retry(monkeypatch):
    from google import genai

    seen = {}
    monkeypatch.setattr(genai, "Client", lambda **kwargs: seen.update(kwargs) or object())
    monkeypatch.setattr(agent, "setting", {"GEMINI_API_KEY": "test-key-from-env"}.get)
    agent.make_provider("gemini").client()
    assert seen["api_key"] == "test-key-from-env" and seen["vertexai"] is False
    options = seen["http_options"]
    assert options.timeout == agent.LIMITS.timeout_seconds * 1000  # milliseconds
    assert options.retry_options.attempts == 1  # the one retry is agent.respond's, not the SDK's
    assert 429 not in options.retry_options.http_status_codes


def test_gemini_without_a_key_never_builds_a_client(monkeypatch):
    from google import genai

    def no_client(**kwargs):
        raise AssertionError("a client was built without a key")

    monkeypatch.setattr(genai, "Client", no_client)
    monkeypatch.setattr(agent, "setting", lambda name: None)
    with pytest.raises(agent.ProviderUnavailable) as raised:
        agent.ask("x", provider="gemini")
    assert raised.value.reason == "auth"


def test_gemini_key_comes_only_from_the_environment_or_streamlit_secrets(monkeypatch):
    import streamlit as st

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(st, "secrets", {})
    assert agent.make_provider("gemini").api_key is None
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")  # the SDK's own variable is not used
    assert agent.make_provider("gemini").api_key is None
    monkeypatch.setattr(st, "secrets", {"GEMINI_API_KEY": "from-secrets"})
    assert agent.make_provider("gemini").api_key == "from-secrets"
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert agent.make_provider("gemini").api_key == "from-env"  # the environment wins
