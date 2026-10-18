"""The AI analyst: Claude answers questions about the public data by calling the fixed tools in
app/ai_analyst/tools.py, and nothing else. A manual tool-use loop, so every call and every
number it saw is recorded and shown next to the answer.

OFF unless BOTH are set (environment variable or Streamlit secret, nowhere else):
    ESG_AI_ENABLED      "true"
    ANTHROPIC_API_KEY   the key
Optional:
    ESG_AI_MODEL        model id, default claude-haiku-4-5
    ESG_AI_EFFORT       low | medium | high; sent only when set (claude-haiku-4-5 rejects it)

Hard limits (LIMITS below; docs/ai_analyst.md): questions per session, tool calls per question,
output tokens per response, question length, request timeout. A refusal by the model stays a
refusal: there is no retry on another model.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from app.ai_analyst import tools as analyst_tools

DEFAULT_MODEL = "claude-haiku-4-5"
REFUSAL_PREFIX = "I can't answer that from the ESG Lens India public data"


@dataclass(frozen=True)
class Limits:
    questions_per_session: int = 10
    tool_calls_per_question: int = 4
    max_output_tokens: int = 1500  # per response; answers are short by instruction
    max_question_chars: int = 500
    timeout_seconds: float = 30.0  # per request
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


def is_enabled() -> bool:
    """On only when ESG_AI_ENABLED is "true" AND an API key is set."""
    switch = (setting("ESG_AI_ENABLED") or "").strip().lower() == "true"
    return switch and bool(setting("ANTHROPIC_API_KEY"))


def disabled_reason() -> str:
    switch = (setting("ESG_AI_ENABLED") or "").strip().lower() == "true"
    if not switch:
        return "ESG_AI_ENABLED is not set to true"
    return "no ANTHROPIC_API_KEY is set"


def model_name() -> str:
    return setting("ESG_AI_MODEL") or DEFAULT_MODEL


def _client():
    import anthropic

    # the key is passed explicitly, so the SDK never falls back to another credential source
    return anthropic.Anthropic(
        api_key=setting("ANTHROPIC_API_KEY"),
        timeout=LIMITS.timeout_seconds,
        max_retries=LIMITS.max_retries,
    )


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


def _request(model: str, messages: list, tool_schemas: list[dict], allow_tools: bool) -> dict:
    request = {
        "model": model,
        "max_tokens": LIMITS.max_output_tokens,
        "system": SYSTEM_PROMPT,
        "tools": tool_schemas,
        "messages": messages,
    }
    if not allow_tools:
        request["tool_choice"] = {"type": "none"}
    effort = setting("ESG_AI_EFFORT")
    if effort:
        request["output_config"] = {"effort": effort}
    return request


def ask(
    question: str, client=None, model: str | None = None, history: list | None = None
) -> Answer:
    """Answer one question within the limits. `history` holds earlier turns to continue a chat."""
    question = check_question(question)
    client = client or _client()
    model = model or model_name()
    tool_schemas = [tool.schema() for tool in analyst_tools.tools()]
    messages = list(history or []) + [{"role": "user", "content": question}]
    answer = Answer(text="", model=model)

    for _ in range(LIMITS.max_requests_per_question):
        allow_tools = len(answer.calls) < LIMITS.tool_calls_per_question
        response = client.messages.create(**_request(model, messages, tool_schemas, allow_tools))
        usage = getattr(response, "usage", None)
        answer.input_tokens += getattr(usage, "input_tokens", 0) or 0
        answer.output_tokens += getattr(usage, "output_tokens", 0) or 0
        answer.stop_reason = response.stop_reason
        answer.model = getattr(response, "model", model) or model
        if response.stop_reason == "refusal":
            # a refusal stays a refusal: shown to the user, never retried on another model
            details = getattr(response, "stop_details", None)
            answer.refusal_category = getattr(details, "category", None)
            answer.text = (
                "The model declined to answer this question (a safety refusal by the model, "
                "not by ESG Lens India). Try asking about the published figures instead."
            )
            return answer
        messages.append({"role": "assistant", "content": response.content})
        uses = [block for block in response.content if getattr(block, "type", "") == "tool_use"]
        if response.stop_reason != "tool_use" or not uses:
            answer.text = "\n".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ).strip()
            if response.stop_reason == "max_tokens":
                answer.text += "\n\n(The answer was cut off at the output limit.)"
            return answer
        results = []
        for block in uses:
            if len(answer.calls) >= LIMITS.tool_calls_per_question:
                # over the limit: the call is not run, the model is told to answer now
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps({"error": LIMIT_REACHED}), "is_error": True})  # fmt: skip
                continue
            call = ToolCall(block.name, dict(block.input or {}))
            try:
                call.result = analyst_tools.call(block.name, call.arguments)
                content, is_error = json.dumps(call.result, default=str), False
            except analyst_tools.ToolArgumentError as error:
                call.error = str(error)
                content, is_error = json.dumps({"error": call.error}), True
            answer.calls.append(call)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})  # fmt: skip
        messages.append({"role": "user", "content": results})

    answer.text = (
        "I stopped at the limit of requests for one question without a final answer. "
        "Please ask a narrower question."
    )
    answer.stop_reason = "max_turns"
    return answer
