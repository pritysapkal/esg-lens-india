"""The AI analyst: Claude answers questions about the public data by calling the fixed tools in
app/ai_analyst/tools.py, and nothing else. A manual tool-use loop, so every call and every
number it saw is recorded and shown next to the answer.

    ANTHROPIC_API_KEY   required; without it the analyst is disabled (the app still works)
    ESG_AI_MODEL        model id, default claude-opus-5-5 (e.g. claude-sonnet-5-5 to spend less)
    ESG_AI_EFFORT       low | medium | high (default medium)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from app.ai_analyst import tools as analyst_tools

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TURNS = 8
REFUSAL_PREFIX = "I can't answer that from the ESG Lens India public data"
# models that accept the server-side refusal fallback (fallbacks="default")
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = f"""You are the analyst of ESG Lens India, a public report card built from the BRSR \
sustainability filings (XBRL) of the NIFTY 50 companies plus Wipro, financial years FY2022-23 to \
FY2025-26. You answer questions for readers who are not specialists, in plain English.

Where the numbers come from
- Every number in your answer must come from a tool result in this conversation. Call the tools \
first; never estimate, recall or compute a figure the tools did not return. When you quote a number, \
say which tool and table it came from, briefly.
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

    @property
    def refused(self) -> bool:
        return self.text.strip().startswith(REFUSAL_PREFIX)


def is_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def model_name() -> str:
    return os.getenv("ESG_AI_MODEL") or DEFAULT_MODEL


def _client():
    import anthropic

    return anthropic.Anthropic()


def _request(model: str, messages: list, tool_schemas: list[dict]) -> dict:
    request = {
        "model": model,
        "max_tokens": 8000,
        "system": SYSTEM_PROMPT,
        "tools": tool_schemas,
        "messages": messages,
        "output_config": {"effort": os.getenv("ESG_AI_EFFORT") or "medium"},
    }
    if model in FALLBACK_MODELS:
        request |= {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    return request


def ask(
    question: str, client=None, model: str | None = None, history: list | None = None
) -> Answer:
    """Answer one question. `history` holds earlier turns (as returned in messages) to continue a chat."""
    client = client or _client()
    model = model or model_name()
    tool_schemas = [tool.schema() for tool in analyst_tools.tools()]
    messages = list(history or []) + [{"role": "user", "content": question}]
    answer = Answer(text="", model=model)

    for _ in range(MAX_TURNS):
        response = client.beta.messages.create(**_request(model, messages, tool_schemas))
        usage = getattr(response, "usage", None)
        answer.input_tokens += getattr(usage, "input_tokens", 0) or 0
        answer.output_tokens += getattr(usage, "output_tokens", 0) or 0
        answer.stop_reason = response.stop_reason
        answer.model = getattr(response, "model", model) or model
        if response.stop_reason == "refusal":
            answer.text = "The model declined to answer this question."
            return answer
        messages.append({"role": "assistant", "content": response.content})
        uses = [block for block in response.content if getattr(block, "type", "") == "tool_use"]
        if response.stop_reason != "tool_use" or not uses:
            answer.text = "\n".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ).strip()
            return answer
        results = []
        for block in uses:
            call = ToolCall(block.name, dict(block.input or {}))
            try:
                call.result = analyst_tools.call(block.name, call.arguments)
                content, is_error = json.dumps(call.result, default=str), False
            except analyst_tools.ToolArgumentError as error:
                call.error = str(error)
                content, is_error = json.dumps({"error": call.error}), True
            answer.calls.append(call)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})

    answer.text = "I stopped after too many tool calls without a final answer. Please ask a narrower question."
    answer.stop_reason = "max_turns"
    return answer
