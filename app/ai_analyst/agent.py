"""The AI analyst: a language model answers questions about the public data by calling the fixed
tools in app/ai_analyst/tools.py, and nothing else. A manual tool-use loop, so every call and
every number it saw is recorded and shown next to the answer. The same loop, tools, guardrails,
limits and refusal handling serve all three providers (app/ai_analyst/providers.py).

OFF unless switched on (environment variable or Streamlit secret, nowhere else):
    ESG_AI_ENABLED      "true" - required for every provider
    ESG_AI_PROVIDER     ollama (default: a free local model, no key) | gemini | anthropic
    GEMINI_API_KEY      required for the gemini provider only (Google AI Studio, free tier)
    ANTHROPIC_API_KEY   required for the anthropic provider only
Optional:
    ESG_AI_MODEL        default qwen2.5:3b (ollama), gemini-3.5-flash-lite (gemini) or
                        claude-haiku-4-5 (anthropic)
    OLLAMA_HOST         default http://127.0.0.1:11434
    ESG_AI_EFFORT       anthropic only; sent only when set (claude-haiku-4-5 rejects it)

Hard limits (LIMITS below; docs/ai_analyst.md): questions per session, tool calls per question,
output tokens per response, question length, request timeout. A refusal by the model stays a
refusal: there is no retry on another model. The public deployment may switch on gemini only
(free tier, per-session limits, a notice to visitors; docs/streamlit_app.md); when Gemini cannot
answer (quota, key, API error) the page falls back to the guided questions.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from app.ai_analyst import providers
from app.ai_analyst import tools as analyst_tools

DEFAULT_PROVIDER = providers.OLLAMA
DEFAULT_MODEL = providers.DEFAULT_MODELS[providers.ANTHROPIC]  # the default of the paid provider
REFUSAL_PREFIX = "I can't answer that from the ESG Lens India public data"
ProviderUnavailable = providers.ProviderUnavailable
API_KEYS = {providers.GEMINI: "GEMINI_API_KEY", providers.ANTHROPIC: "ANTHROPIC_API_KEY"}


@dataclass(frozen=True)
class Limits:
    questions_per_session: int = 10
    tool_calls_per_question: int = 4
    max_output_tokens: int = 1500  # per response; answers are short by instruction
    max_question_chars: int = 500
    timeout_seconds: float = 30.0  # per request to the Gemini or Anthropic API
    local_timeout_seconds: float = (
        180.0  # per request to Ollama: a small model on a laptop CPU is slow
    )
    local_context_tokens: int = 8192  # Ollama context window (its default would cut the prompt)
    max_retries: int = 1  # the SDK retries only connection errors, 408, 409, 429 and 5xx

    @property
    def max_requests_per_question(self) -> int:
        # one request per round of tool calls, plus the final answer
        return self.tool_calls_per_question + 1


LIMITS = Limits()

SYSTEM_PROMPT = f"""You are the analyst of ESG Lens India, a public report card built from the BRSR \
sustainability filings (XBRL) of the NIFTY 50 companies plus Wipro, financial years FY2022-23 to \
FY2025-26. You answer questions for readers who are not specialists, in plain English.

Where the numbers come from
- Every number in your answer must come from a tool result in this conversation. Call the tools \
first; never estimate, recall or compute a figure the tools did not return. When you quote a number, \
say which tool and table it came from, briefly.
- You may make at most {LIMITS.tool_calls_per_question} tool calls per question, so choose them \
carefully and ask for exactly the group, company and year you need.
- The tools return only values ESG Lens India calculates (intensities, shares, medians, ranks, \
percentiles, scores, counts). Filed absolute values - tonnes, energy, water, turnover, headcounts - \
are not available and must not be guessed.
- Do not build group figures yourself from company figures (for example by averaging company \
intensities). Use group_metric: "whole group" is the sum over the sum, "typical company" is the median.

Saying how far a number can be trusted
- If a figure is withheld because fewer than 5 companies stand behind it, say so ("withheld: fewer \
than 5 companies") instead of giving a number.
- FY2025-26 is provisional: no later report has confirmed it yet. Say so whenever you use it.
- Restatements of the latest year are not observable yet; a year-on-year move that is not confirmed \
is not a ranking.

How to speak about results
- Describe associations, never causes. Use "is associated with", "went together with", "moved \
from ... to ...". Do not write that something causes, drives, leads to or results in something else.
- The Disclosure Quality Score measures how well a company discloses, not its ESG performance; it is \
not an ESG rating. Nothing you say is investment advice.
- Keep it short: the answer first, then the numbers, then one line on caveats.

Questions you must not answer
- Questions outside this data - share prices, forecasts, investment recommendations, companies or \
years not covered, filed absolute values, personal opinions, anything unrelated to ESG Lens India - \
get no tool call. Reply with a sentence that starts exactly with "{REFUSAL_PREFIX}", then say in \
one line what you can answer instead."""

LIMIT_REACHED = (
    f"Tool-call limit reached ({LIMITS.tool_calls_per_question} per question). Answer now from the "
    "tool results you already have, and say what you could not look up."
)


@dataclass
class ToolCall:
    name: str
    arguments: dict
    result: dict | None = None
    error: str | None = None


@dataclass
class Answer:
    text: str
    calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    refusal_category: str | None = None
    provider: str = ""
    seconds: float = 0.0  # wall-clock time of the whole question

    @property
    def model_refused(self) -> bool:
        """The model's safety classifier declined the request (stop_reason "refusal")."""
        return self.stop_reason == "refusal"

    @property
    def refused(self) -> bool:
        """Out of scope: the analyst said it cannot answer, or the model declined."""
        return self.model_refused or self.text.strip().startswith(REFUSAL_PREFIX)


class QuestionRejected(ValueError):
    """The question breaks a limit before any request is sent (shown to the user)."""


# ------------------------------------------------------------------ settings: env or st.secrets


def setting(name: str) -> str | None:
    """A setting from the environment, else from Streamlit secrets. Nothing else is read: no
    file of this project, no default credential profile."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # no secrets file, or not running under Streamlit
        return None
    return str(value) if value else None


def provider_name() -> str:
    name = (setting("ESG_AI_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    return name if name in providers.PROVIDERS else f"unknown:{name}"


def _switched_on() -> bool:
    return (setting("ESG_AI_ENABLED") or "").strip().lower() == "true"


def is_enabled() -> bool:
    """On only when ESG_AI_ENABLED is "true", the provider is known and - for the gemini and
    anthropic providers - its API key is set. The local provider needs no key."""
    if not _switched_on():
        return False
    name = provider_name()
    if name in API_KEYS:
        return bool(setting(API_KEYS[name]))
    return name == providers.OLLAMA


def switched_on() -> bool:
    """ESG_AI_ENABLED is "true", whether or not the provider has what it needs."""
    return _switched_on()


def disabled_reason() -> str:
    """Why the analyst is off - for the developer (terminal, eval), never shown to visitors."""
    if not _switched_on():
        return "ESG_AI_ENABLED is not set to true"
    name = provider_name()
    if name not in providers.PROVIDERS:
        return f"ESG_AI_PROVIDER must be one of {', '.join(providers.PROVIDERS)}"
    return f"no {API_KEYS.get(name, 'API key')} is set"


def sends_questions_to_google() -> bool:
    """The configured provider is Gemini: visitors must be told before they ask."""
    return provider_name() == providers.GEMINI


def model_name(provider: str | None = None) -> str:
    provider = provider or provider_name()
    return setting("ESG_AI_MODEL") or providers.DEFAULT_MODELS.get(provider, DEFAULT_MODEL)


def make_provider(name: str | None = None, client=None):
    """The provider object, with the limits applied (timeouts, retries, context window)."""
    name = name or provider_name()
    if name == providers.GEMINI:
        return providers.GeminiProvider(
            client=client,
            api_key=setting("GEMINI_API_KEY"),
            timeout=LIMITS.timeout_seconds,
            max_retries=LIMITS.max_retries,
        )
    if name == providers.ANTHROPIC:
        return providers.AnthropicProvider(
            client=client,
            api_key=setting("ANTHROPIC_API_KEY"),
            timeout=LIMITS.timeout_seconds,
            max_retries=LIMITS.max_retries,
        )
    if name == providers.OLLAMA:
        return providers.OllamaProvider(
            client=client,
            host=setting("OLLAMA_HOST"),
            timeout=LIMITS.local_timeout_seconds,
            num_ctx=LIMITS.local_context_tokens,
        )
    raise ValueError(f"unknown provider {name!r}")


def check_question(question: str, asked_so_far: int = 0) -> str:
    """The question, stripped, or QuestionRejected when a limit says no."""
    if asked_so_far >= LIMITS.questions_per_session:
        raise QuestionRejected(
            f"This session has used its {LIMITS.questions_per_session} questions. "
            "Reload the page to start a new session."
        )
    question = (question or "").strip()
    if not question:
        raise QuestionRejected("Please type a question.")
    if len(question) > LIMITS.max_question_chars:
        raise QuestionRejected(
            f"Please keep the question under {LIMITS.max_question_chars} characters."
        )
    return question


def ask(
    question: str,
    client=None,
    model: str | None = None,
    history: list | None = None,
    provider: str | None = None,
) -> Answer:
    """Answer one question within the limits. `client` replaces the provider's client (tests);
    `history` holds earlier turns in the provider's message format. Raises ProviderUnavailable
    when the provider cannot answer at all (e.g. the Gemini free-tier quota is used up)."""
    question = check_question(question)
    name = provider or provider_name()
    backend = make_provider(name, client=client)
    model = model or model_name(name)
    session = backend.session(
        model, SYSTEM_PROMPT, analyst_tools.tools(), question, history,
        LIMITS.max_output_tokens, setting("ESG_AI_EFFORT") if name == providers.ANTHROPIC else None,
    )  # fmt: skip
    answer = Answer(text="", model=model, provider=name)
    started = time.perf_counter()

    def done(text: str, stop_reason: str | None = None) -> Answer:
        answer.text = text
        if stop_reason:
            answer.stop_reason = stop_reason
        answer.seconds = time.perf_counter() - started
        return answer

    for _ in range(LIMITS.max_requests_per_question):
        allow_tools = len(answer.calls) < LIMITS.tool_calls_per_question
        turn = session.respond(allow_tools)
        answer.input_tokens += turn.input_tokens
        answer.output_tokens += turn.output_tokens
        answer.stop_reason = turn.stop_reason
        answer.model = turn.model or model
        if turn.stop_reason == "refusal":
            # a refusal stays a refusal: shown to the user, never retried on another model
            answer.refusal_category = turn.refusal_category
            return done(
                "The model declined to answer this question (a safety refusal by the model, "
                "not by ESG Lens India). Try asking about the published figures instead."
            )
        if not turn.tool_uses:
            text = turn.text or "The model gave no answer. Please rephrase the question."
            if turn.stop_reason == "max_tokens":
                text += "\n\n(The answer was cut off at the output limit.)"
            return done(text)
        results = []
        for use in turn.tool_uses:
            if len(answer.calls) >= LIMITS.tool_calls_per_question:
                # over the limit: the call is not run, the model is told to answer now
                results.append((use, json.dumps({"error": LIMIT_REACHED}), True))
                continue
            call = ToolCall(use.name, dict(use.arguments))
            try:
                call.result = analyst_tools.call(use.name, call.arguments)
                results.append((use, json.dumps(call.result, default=str), False))
            except analyst_tools.ToolArgumentError as error:
                call.error = str(error)
                results.append((use, json.dumps({"error": call.error}), True))
            answer.calls.append(call)
        session.add_tool_results(results)

    return done(
        "I stopped at the limit of requests for one question without a final answer. "
        "Please ask a narrower question.",
        "max_turns",
    )
