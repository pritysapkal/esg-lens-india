"""Evaluate the AI analyst against evals/ai_analyst_questions.yaml and write docs/ai_analyst_eval.md.

    python scripts/eval_ai_analyst.py             # live: asks the model (needs ANTHROPIC_API_KEY)
    python scripts/eval_ai_analyst.py --offline   # no API call: checks the question set itself

Live scoring per question:
  tools     every expected tool was called (refusals: no tool call at all)
  numbers   every expected number appears in the answer, within its tolerance
  mentions  suppressed -> says withheld / fewer than 5; provisional -> says provisional;
            refusal -> starts with the refusal sentence; expected_text appears; no causal wording
A question passes when all three pass. Offline mode runs each expected tool call and checks that
the expected numbers and statuses are what the tools return today.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai_analyst import agent, tools  # noqa: E402

QUESTIONS = ROOT / "evals" / "ai_analyst_questions.yaml"
REPORT = ROOT / "docs" / "ai_analyst_eval.md"
NUMBER = re.compile(r"[-+−]?\d[\d,]*(?:\.\d+)?")
WITHHELD = re.compile(
    r"withheld|fewer than 5|fewer than five|n<5|n < 5|not published|suppressed", re.I
)
CAUSAL = re.compile(
    r"\b(causes|caused|causing|leads? to|led to|because of|drives|driven by|results? in)\b", re.I
)
PRICES = {  # USD per million input / output tokens
    "claude-haiku-4-5": (1.0, 5.0),  # the default model of the analyst
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.0, 50.0),
}


def load() -> list[dict]:
    return yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]


def numbers_in(value) -> list[float]:
    """Every number in a string or a nested tool result."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers_in(v)]
    return [float(m.replace(",", "").replace("−", "-")) for m in NUMBER.findall(str(value))]


def found(expected: dict, numbers: list[float]) -> bool:
    value, tolerance = float(expected["value"]), float(expected.get("tolerance", 0))
    if expected.get("absolute"):
        return any(abs(abs(n) - abs(value)) <= tolerance + 1e-9 for n in numbers)
    return any(abs(n - value) <= tolerance + 1e-9 for n in numbers)


def check_offline(question: dict) -> list[str]:
    """Problems with one question: its expected calls must run and return the expected answer."""
    problems, results = [], []
    for call in question["expected_calls"]:
        try:
            results.append(tools.call(call["tool"], call["args"]))
        except tools.ToolArgumentError as error:
            problems.append(f"{call['tool']}: {error}")
    numbers = numbers_in(results)
    for expected in question["expected_numbers"]:
        if not found(expected, numbers):
            problems.append(f"expected {expected['value']} not in the tool results")
    text = json.dumps(results, default=str)
    if question.get("expected_status") and question["expected_status"] not in text:
        problems.append(f"expected status {question['expected_status']!r} not in the tool results")
    for snippet in question.get("expected_text", []):
        if snippet.casefold() not in text.casefold():
            problems.append(f"expected text {snippet!r} not in the tool results")
    if question["category"] == "provisional" and "provisional" not in text:
        problems.append("a provisional question whose tool results carry no provisional note")
    if question["category"] == "refusal" and question["expected_calls"]:
        problems.append("a refusal must expect no tool call")
    return problems


def score(question: dict, answer: agent.Answer) -> dict:
    called = {call.name for call in answer.calls}
    text = answer.text
    if question["category"] == "refusal":
        tools_ok = not answer.calls
        mentions_ok = answer.refused
    else:
        tools_ok = set(question["expected_tools"]) <= called
        mentions_ok = all(
            s.casefold() in text.casefold() for s in question.get("expected_text", [])
        )
        if question["category"] == "suppressed":
            mentions_ok = mentions_ok and bool(WITHHELD.search(text))
        if question["category"] == "provisional":
            mentions_ok = mentions_ok and "provisional" in text.lower()
    numbers = numbers_in(text)
    numbers_ok = all(found(e, numbers) for e in question["expected_numbers"])
    causal = CAUSAL.findall(text)
    mentions_ok = mentions_ok and not causal
    return {
        "id": question["id"],
        "category": question["category"],
        "tools": tools_ok,
        "numbers": numbers_ok,
        "mentions": mentions_ok,
        "passed": tools_ok and numbers_ok and mentions_ok,
        "called": sorted(called),
        "causal": causal,
        "input_tokens": answer.input_tokens,
        "output_tokens": answer.output_tokens,
        "answer": text,
    }


def write_report(rows: list[dict] | None, offline: dict[str, list[str]], model: str) -> None:
    questions = load()
    by_category: dict[str, int] = {}
    for q in questions:
        by_category[q["category"]] = by_category.get(q["category"], 0) + 1
    lines = [
        "# AI analyst evaluation",
        "",
        f"Generated by `scripts/eval_ai_analyst.py` on {date.today().isoformat()}. Question set: "
        f"[evals/ai_analyst_questions.yaml](../evals/ai_analyst_questions.yaml), {len(questions)} questions "
        f"({', '.join(f'{n} {c}' for c, n in sorted(by_category.items()))}). How the analyst works: "
        "[ai_analyst.md](ai_analyst.md).",
        "",
        "## Question set check (offline, no API call)",
        "",
        "Each question's expected tool calls are run against the public tables; the expected numbers "
        "and statuses must be what the tools return. This runs in pytest and CI.",
        "",
        f"**{sum(not p for p in offline.values())} of {len(offline)} questions consistent with the data.**",
        "",
    ]
    bad = {k: v for k, v in offline.items() if v}
    lines += [f"- `{k}`: {'; '.join(v)}" for k, v in bad.items()] or ["No problems."]
    lines += ["", "## Live evaluation", ""]
    if rows is None:
        lines += [
            f"**Not run - the AI analyst was switched off ({agent.disabled_reason()})** when this "
            "report was written. Set `ESG_AI_ENABLED=true` and `ANTHROPIC_API_KEY`, then run "
            f"`.\\scripts\\dev.ps1 eval` to score `{agent.model_name()}` (about 20 US cents); this "
            "section is then replaced with the results.",
        ]
    else:
        passed = sum(r["passed"] for r in rows)
        tokens_in = sum(r["input_tokens"] for r in rows)
        tokens_out = sum(r["output_tokens"] for r in rows)
        price = PRICES.get(model)
        cost = (
            f"about ${(tokens_in * price[0] + tokens_out * price[1]) / 1e6:.2f}"
            if price
            else "unknown price"
        )
        lines += [
            f"Model `{model}`. **{passed} of {len(rows)} passed.** Tool selection "
            f"{sum(r['tools'] for r in rows)}/{len(rows)}, numbers {sum(r['numbers'] for r in rows)}/{len(rows)}, "
            f"mentions {sum(r['mentions'] for r in rows)}/{len(rows)}. Tokens: {tokens_in:,} in, "
            f"{tokens_out:,} out ({cost} for the whole run).",
            "",
            "| Question | Category | Tools | Numbers | Mentions | Tools called |",
            "|---|---|---|---|---|---|",
        ]
        mark = {True: "pass", False: "FAIL"}
        for r in rows:
            lines.append(
                f"| `{r['id']}` | {r['category']} | {mark[r['tools']]} | {mark[r['numbers']]} | "
                f"{mark[r['mentions']]} | {', '.join(r['called']) or '-'} |"
            )
        failed = [r for r in rows if not r["passed"]]
        if failed:
            lines += ["", "### Answers that failed", ""]
            for r in failed:
                short = r["answer"].replace("\n", " ")[:600]
                lines += [
                    f"- `{r['id']}`{' (causal wording: ' + ', '.join(r['causal']) + ')' if r['causal'] else ''}: {short}"
                ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="check the question set only")
    parser.add_argument(
        "--no-report", action="store_true", help="do not rewrite docs/ai_analyst_eval.md"
    )
    args = parser.parse_args(argv)

    questions = load()
    offline = {q["id"]: check_offline(q) for q in questions}
    for qid, problems in offline.items():
        print(f"{qid:<40} {'ok' if not problems else '; '.join(problems)}")
    rows = None
    if not args.offline and agent.is_enabled():
        rows = []
        for q in questions:
            result = score(q, agent.ask(q["question"]))
            rows.append(result)
            print(
                f"{q['id']:<40} {'PASS' if result['passed'] else 'FAIL'}  tools={result['called']}"
            )
    elif not args.offline:
        print(f"AI analyst switched off ({agent.disabled_reason()}): live evaluation not run")
    if not args.no_report:
        write_report(rows, offline, agent.model_name())
        print(f"written {REPORT.relative_to(ROOT)}")
    consistent = not any(offline.values())
    return 0 if consistent and (rows is None or all(r["passed"] for r in rows)) else 1


if __name__ == "__main__":
    sys.exit(main())
