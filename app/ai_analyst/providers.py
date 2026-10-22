"""The three model back-ends of the AI analyst behind one small interface, so that the loop in
agent.py - the tools, the guardrails, the limits and the refusal handling - is the same for all.

    gemini      Google Gemini through the Gemini API on Google's free tier (needs an API key,
                passed in by agent.py; the free tier has per-minute and daily quotas)
    ollama      a small open model on this laptop through Ollama (free, no key, no network
                beyond localhost; see docs/ai_analyst.md for the model and how to install it)
    anthropic   Claude through the Anthropic API (needs an API key, passed in by agent.py; paid per token)

A provider opens a Session for one question. The session keeps the conversation in the
provider's own message format, sends one request per `respond()` and turns the reply into a
neutral `Turn`; `add_tool_results()` appends the results of the tools the loop ran. A provider
that cannot answer at all (quota used up, key rejected, API down) raises ProviderUnavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

ANTHROPIC = "anthropic"
OLLAMA = "ollama"
GEMINI = "gemini"
PROVIDERS = (GEMINI, OLLAMA, ANTHROPIC)

DEFAULT_MODELS = {
    ANTHROPIC: "claude-haiku-4-5",
    # chosen for this laptop (16 GB RAM, no GPU): docs/ai_analyst.md, "Local model"
    OLLAMA: "qwen2.5:3b",
    # stable, function calling, on the free tier: docs/ai_analyst.md, "Gemini" (checked 2026-10-20)
    GEMINI: "gemini-3.5-flash-lite",
}


class ProviderUnavailable(RuntimeError):
    """The provider cannot answer right now. `reason`: "quota" (free-tier quota used up),
    "auth" (key missing or rejected) or "error" (API error, timeout, network). `transient`: a
    server error (5xx) or a timeout, which agent.ask retries once."""

    def __init__(self, reason: str, detail: str = "", transient: bool = False):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.transient = transient


def is_transient(error: Exception) -> bool:
    """A server error (5xx) or a timeout of any provider: worth one retry. Never a used-up
    quota (429), a rejected key or a bad request; a refusal is an answer, not an error."""
    if isinstance(error, ProviderUnavailable):
        return error.transient
    if isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower():
        return True  # TimeoutError, httpx.*Timeout, anthropic.APITimeoutError
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    return isinstance(code, int) and (code == 408 or 500 <= code <= 599)


DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


@dataclass
class ToolUse:
    id: str
    name: str
    arguments: dict


@dataclass
class Turn:
    """One reply of the model, whatever the provider."""

    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
    # "end" | "tool_use" | "max_tokens" | "refusal"
    stop_reason: str = "end"
    refusal_category: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    seconds: float = 0.0


# ------------------------------------------------------------------ Anthropic


class AnthropicSession:
    def __init__(
        self,
        client,
        model: str,
        system: str,
        tools: list[dict],
        messages: list,
        max_tokens: int,
        effort: str | None,
    ):
        self.client, self.model, self.system, self.tools = client, model, system, tools
        self.messages, self.max_tokens, self.effort = messages, max_tokens, effort
        self.last_request: dict | None = None

    def respond(self, allow_tools: bool) -> Turn:
        request = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self.system,
            "tools": self.tools,
            "messages": self.messages,
        }
        if not allow_tools:
            request["tool_choice"] = {"type": "none"}
        if self.effort:
            request["output_config"] = {"effort": self.effort}
        self.last_request = request
        response = self.client.messages.create(**request)
        usage = getattr(response, "usage", None)
        turn = Turn(
            stop_reason={
                "tool_use": "tool_use",
                "max_tokens": "max_tokens",
                "refusal": "refusal",
            }.get(response.stop_reason, "end"),
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            model=getattr(response, "model", self.model) or self.model,
        )
        if response.stop_reason == "refusal":
            turn.refusal_category = getattr(
                getattr(response, "stop_details", None), "category", None
            )
            return turn
        content = list(response.content)
        turn.text = "\n".join(b.text for b in content if getattr(b, "type", "") == "text").strip()
        turn.tool_uses = [
            ToolUse(b.id, b.name, dict(b.input or {}))
            for b in content
            if getattr(b, "type", "") == "tool_use"
        ]
        self.messages.append({"role": "assistant", "content": content})
        return turn

    def add_tool_results(self, results: list[tuple[ToolUse, str, bool]]) -> None:
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": content,
                        "is_error": is_error,
                    }
                    for use, content, is_error in results
                ],
            }
        )


class AnthropicProvider:
    name = ANTHROPIC

    def __init__(
        self, client=None, api_key: str | None = None, timeout: float = 30.0, max_retries: int = 1
    ):
        self._client, self.api_key, self.timeout, self.max_retries = (
            client,
            api_key,
            timeout,
            max_retries,
        )

    def client(self):
        if self._client is None:
            import anthropic

            # the key is passed explicitly, so the SDK never falls back to another credential source
            self._client = anthropic.Anthropic(
                api_key=self.api_key, timeout=self.timeout, max_retries=self.max_retries
            )
        return self._client

    def session(
        self,
        model: str,
        system: str,
        tools: list,
        question: str,
        history: list | None,
        max_tokens: int,
        effort: str | None = None,
    ):
        schemas = [tool.schema() for tool in tools]
        messages = list(history or []) + [{"role": "user", "content": question}]
        return AnthropicSession(self.client(), model, system, schemas, messages, max_tokens, effort)


# ------------------------------------------------------------------ Ollama


def ollama_tool(tool) -> dict:
    """The same tool definition in Ollama's (OpenAI-style) function format."""
    schema = tool.schema()
    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["input_schema"],
        },
    }


class OllamaSession:
    def __init__(self, client, model: str, tools: list[dict], messages: list, options: dict):
        self.client, self.model, self.tools, self.messages, self.options = (
            client,
            model,
            tools,
            messages,
            options,
        )
        self.last_request: dict | None = None
        self._calls = 0

    def respond(self, allow_tools: bool) -> Turn:
        # Ollama has no tool_choice: past the tool-call limit the tools are simply not offered
        request = {
            "model": self.model,
            "messages": self.messages,
            "options": self.options,
            "stream": False,
        }
        if allow_tools:
            request["tools"] = self.tools
        self.last_request = request
        response = self.client.chat(**request)
        message = _get(response, "message")
        calls = _get(message, "tool_calls") or []
        turn = Turn(
            text=(_get(message, "content") or "").strip(),
            input_tokens=_get(response, "prompt_eval_count") or 0,
            output_tokens=_get(response, "eval_count") or 0,
            model=_get(response, "model") or self.model,
            seconds=(_get(response, "total_duration") or 0) / 1e9,
        )
        for call in calls:
            function = _get(call, "function")
            arguments = _get(function, "arguments") or {}
            if isinstance(arguments, str):  # some models send a JSON string
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"_unparsed": arguments}
            self._calls += 1
            turn.tool_uses.append(
                ToolUse(f"call_{self._calls}", _get(function, "name") or "", dict(arguments))
            )
        if turn.tool_uses:
            turn.stop_reason = "tool_use"
        elif _get(response, "done_reason") == "length":
            turn.stop_reason = "max_tokens"
        assistant = {"role": "assistant", "content": _get(message, "content") or ""}
        if calls:
            assistant["tool_calls"] = [
                {"function": {"name": use.name, "arguments": use.arguments}}
                for use in turn.tool_uses
            ]
        self.messages.append(assistant)
        return turn

    def add_tool_results(self, results: list[tuple[ToolUse, str, bool]]) -> None:
        for use, content, _is_error in results:
            self.messages.append({"role": "tool", "content": content, "tool_name": use.name})


class OllamaProvider:
    name = OLLAMA

    def __init__(
        self, client=None, host: str | None = None, timeout: float = 180.0, num_ctx: int = 8192
    ):
        self._client, self.host, self.timeout, self.num_ctx = (
            client,
            host or DEFAULT_OLLAMA_HOST,
            timeout,
            num_ctx,
        )

    def client(self):
        if self._client is None:
            import ollama

            self._client = ollama.Client(host=self.host, timeout=self.timeout)
        return self._client

    def session(
        self,
        model: str,
        system: str,
        tools: list,
        question: str,
        history: list | None,
        max_tokens: int,
        effort: str | None = None,
    ):
        messages = (
            [{"role": "system", "content": system}]
            + list(history or [])
            + [{"role": "user", "content": question}]
        )
        # a fixed context window: Ollama's default is small and it cuts long prompts silently
        options = {"num_predict": max_tokens, "num_ctx": self.num_ctx, "temperature": 0}
        return OllamaSession(
            self.client(), model, [ollama_tool(t) for t in tools], messages, options
        )


# ------------------------------------------------------------------ Gemini

# finish reasons of a Gemini candidate that mean Google's safety system declined
GEMINI_REFUSALS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}


def gemini_tool(tool) -> dict:
    """The same tool definition as a Gemini function declaration (the JSON schema as is)."""
    schema = tool.schema()
    return {
        "name": schema["name"],
        "description": schema["description"],
        "parameters_json_schema": schema["input_schema"],
    }


def gemini_error(error: Exception) -> ProviderUnavailable:
    """An exception of the Gemini SDK (or of the network under it) as ProviderUnavailable."""
    code = getattr(error, "code", None)
    status = str(getattr(error, "status", "") or "")
    text = str(error)
    if code == 429 or "RESOURCE_EXHAUSTED" in status + text:
        reason = "quota"
    elif code in (401, 403) or "API_KEY_INVALID" in text or status == "PERMISSION_DENIED":
        reason = "auth"
    else:
        reason = "error"
    return ProviderUnavailable(
        reason,
        f"{type(error).__name__} {code or ''}".strip(),
        transient=reason == "error" and is_transient(error),
    )


def _name(value) -> str:
    """An SDK enum (or a plain string in tests) as its upper-case name."""
    return str(getattr(value, "name", value) or "").upper()


class GeminiSession:
    def __init__(self, client, model: str, config: dict, contents: list):
        self.client, self.model, self.config, self.contents = client, model, config, contents
        self.last_request: dict | None = None
        self._calls = 0

    def respond(self, allow_tools: bool) -> Turn:
        # past the tool-call limit the model may not call a function (mode NONE)
        config = dict(self.config)
        config["tool_config"] = {
            "function_calling_config": {"mode": "AUTO" if allow_tools else "NONE"}
        }
        request = {"model": self.model, "contents": self.contents, "config": config}
        self.last_request = request
        try:
            response = self.client.models.generate_content(**request)
        except Exception as error:  # quota, key, API or network: the page falls back to guided
            raise gemini_error(error) from error
        usage = _get(response, "usage_metadata")
        turn = Turn(
            input_tokens=_get(usage, "prompt_token_count") or 0,
            output_tokens=(_get(usage, "candidates_token_count") or 0)
            + (_get(usage, "thoughts_token_count") or 0),
            model=_get(response, "model_version") or self.model,
        )
        blocked = _name(_get(_get(response, "prompt_feedback"), "block_reason"))
        blocked = "" if blocked == "BLOCKED_REASON_UNSPECIFIED" else blocked
        candidates = _get(response, "candidates") or []
        if blocked or not candidates:
            # the question itself was blocked: a refusal, never retried on another model
            turn.stop_reason, turn.refusal_category = "refusal", (blocked or "blocked").lower()
            return turn
        candidate = candidates[0]
        finish = _name(_get(candidate, "finish_reason"))
        if finish in GEMINI_REFUSALS:
            turn.stop_reason, turn.refusal_category = "refusal", finish.lower()
            return turn
        content = _get(candidate, "content")
        parts = _get(content, "parts") or []
        turn.text = "\n".join(
            _get(p, "text") for p in parts if _get(p, "text") and not _get(p, "thought")
        ).strip()
        for part in parts:
            call = _get(part, "function_call")
            if not call:
                continue
            self._calls += 1
            turn.tool_uses.append(
                ToolUse(
                    _get(call, "id") or f"call_{self._calls}",
                    _get(call, "name") or "",
                    dict(_get(call, "args") or {}),
                )
            )
        if turn.tool_uses:
            turn.stop_reason = "tool_use"
        elif finish == "MAX_TOKENS":
            turn.stop_reason = "max_tokens"
        # the model's turn goes back exactly as received (it carries Gemini's thought signatures)
        self.contents.append(content)
        return turn

    def add_tool_results(self, results: list[tuple[ToolUse, str, bool]]) -> None:
        parts = []
        for use, content, is_error in results:
            payload = json.loads(content)
            function_response = {
                "name": use.name,
                "response": payload if is_error else {"output": payload},
            }
            if not use.id.startswith("call_"):  # an id the API gave (ours are local counters)
                function_response["id"] = use.id
            parts.append({"function_response": function_response})
        self.contents.append({"role": "user", "parts": parts})


class GeminiProvider:
    name = GEMINI

    def __init__(
        self, client=None, api_key: str | None = None, timeout: float = 30.0, max_retries: int = 1
    ):
        self._client, self.api_key, self.timeout, self.max_retries = (
            client,
            api_key,
            timeout,
            max_retries,
        )

    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ProviderUnavailable("auth", "no Gemini API key")
            from google import genai
            from google.genai import types

            # the key is passed explicitly and Vertex AI is off, so the SDK never falls back to
            # another credential source or to a (billed) Google Cloud project
            self._client = genai.Client(
                api_key=self.api_key,
                vertexai=False,
                http_options=types.HttpOptions(
                    timeout=int(self.timeout * 1000),  # milliseconds
                    # agent.ask makes the one retry of a 5xx or timeout; here 429 is never
                    # retried either way: a used-up quota stays used up
                    retry_options=types.HttpRetryOptions(
                        attempts=1 + self.max_retries,
                        http_status_codes=[408, 500, 502, 503, 504],
                    ),
                ),
            )
        return self._client

    def session(
        self,
        model: str,
        system: str,
        tools: list,
        question: str,
        history: list | None,
        max_tokens: int,
        effort: str | None = None,
    ):
        config = {
            "system_instruction": system,
            "tools": [{"function_declarations": [gemini_tool(t) for t in tools]}],
            "max_output_tokens": max_tokens,
            "temperature": 0,
            # the loop in agent.py runs the tools itself, with its validation and limits
            "automatic_function_calling": {"disable": True},
        }
        contents = list(history or []) + [{"role": "user", "parts": [{"text": question}]}]
        return GeminiSession(self.client(), model, config, contents)


def _get(obj, name):
    """A field of an SDK response object or of a plain dict (tests use dicts)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
