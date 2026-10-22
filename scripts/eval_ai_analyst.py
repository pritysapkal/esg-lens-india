"""Evaluate the AI analyst against evals/ai_analyst_questions.yaml and write docs/ai_analyst_eval.md.

    python scripts/eval_ai_analyst.py                    # live, with the configured provider
    python scripts/eval_ai_analyst.py --provider ollama --model qwen2.5:3b
    python scripts/eval_ai_analyst.py --provider gemini         # free tier; paced (--pause)
    python scripts/eval_ai_analyst.py --offline          # no model call: checks the question set
    python scripts/eval_ai_analyst.py --report-only      # rebuild the report from saved results

The live run needs ESG_AI_ENABLED=true (and GEMINI_API_KEY for gemini, ANTHROPIC_API_KEY for
anthropic). Each live run is saved to evals/results/<provider>__<model>.json; the report shows
every saved run, and a "pending" row for each provider in PENDING that has no saved run yet.

Gemini's free tier has per-minute and daily quotas, so a gemini run pauses between questions
(--pause, default GEMINI_PAUSE seconds). If the quota runs out, the question is retried once
after a minute (a per-minute quota refills); if it is still out, the run stops and nothing is
saved - a run with quota failures would not be comparable. Run it again later.

Live scoring per question:
  tools     every expected tool was called (refusals: no tool call at all)
  numbers   every expected number appears in the answer, within its tolerance
  mentions  suppressed -> says withheld / fewer than 5; provisional -> says provisional;
            refusal -> starts with the refusal sentence; expected_text appears; no causal wording;
            no caveat that does not apply (the Disclosure Quality Score caveat in an answer about
            another figure, "provisional" for final years)
A question passes when all three pass. Offline mode runs each expected tool call and checks that
the expected numbers and statuses are what the tools return today.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai_analyst import agent, tools  # noqa: E402

QUESTIONS = ROOT / "evals" / "ai_analyst_questions.yaml"
REPORT = ROOT / "docs" / "ai_analyst_eval.md"
RESULTS = ROOT / "evals" / "results"
NUMBER = re.compile(r"[-+−]?\d[\d,]*(?:\.\d+)?")
WITHHELD = re.compile(
    r"withheld|fewer than 5|fewer than five|n<5|n < 5|not published|suppressed", re.I
)
DQS_QUESTION = re.compile(r"disclosure quality|\bDQS\b|\bscore\b", re.I)
DQS_CAVEAT = re.compile(r"disclosure quality score|\bDQS\b|not an ESG rating", re.I)
YEAR = re.compile(r"FY\d{4}-\d{2}")
PROVISIONAL_YEAR = "FY2025-26"  # the latest year, not yet confirmed by a later report
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
# providers whose evaluation is still to be run (on the owner's machine, with their own key)
PENDING = {"gemini": ("gemini-3.5-flash-lite", "pending — run locally by Prity")}
GEMINI_PAUSE = 10.0  # seconds between questions of a gemini run (free-tier per-minute quota)
QUOTA_WAIT = 65.0  # seconds before the one retry of a question that hit the quota


class QuotaExhausted(RuntimeError):
    """The provider's quota is used up: the live run stops without saving."""


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


def irrelevant_caveats(question: dict, text: str) -> list[str]:
    """Caveats the answer adds that do not apply to the question: the Disclosure Quality Score
    caveat in an answer that is not about the score, or "provisional" in an answer about named
    years that are all final."""
    asked = question.get("question", "")
    found_caveats = []
    if not DQS_QUESTION.search(asked) and DQS_CAVEAT.search(text):
        found_caveats.append("Disclosure Quality Score caveat")
    years = set(YEAR.findall(asked))
    if years and PROVISIONAL_YEAR not in years and "provisional" in text.lower():
        found_caveats.append("provisional note")
    return found_caveats


def score(
    question: dict, answer: agent.Answer | None, error: str | None = None, seconds: float = 0.0
) -> dict:
    """One question. An error (timeout, connection) counts as a failure, not a crash."""
    if answer is None:
        answer = agent.Answer(text="")
    called = {call.name for call in answer.calls}
    text = answer.text
    refusal = question["category"] == "refusal"
    if refusal:
        tools_ok = not answer.calls
        refusal_ok = answer.refused and not answer.calls
        mentions_ok = refusal_ok
    else:
        tools_ok = set(question["expected_tools"]) <= called
        refusal_ok = not answer.refused  # a question it should answer must not be refused
        mentions_ok = refusal_ok and all(
            s.casefold() in text.casefold() for s in question.get("expected_text", [])
        )
        if question["category"] == "suppressed":
            mentions_ok = mentions_ok and bool(WITHHELD.search(text))
        if question["category"] == "provisional":
            mentions_ok = mentions_ok and "provisional" in text.lower()
    numbers = numbers_in(text)
    numbers_ok = all(found(e, numbers) for e in question["expected_numbers"])
    causal = CAUSAL.findall(text)
    irrelevant = [] if refusal else irrelevant_caveats(question, text)
    mentions_ok = mentions_ok and not causal and not irrelevant
    if error:
        tools_ok = numbers_ok = mentions_ok = refusal_ok = False
    return {
        "id": question["id"],
        "category": question["category"],
        "has_numbers": bool(question["expected_numbers"]),
        "tools": tools_ok,
        "numbers": numbers_ok,
        "refusal_ok": refusal_ok,
        "mentions": mentions_ok,
        "passed": tools_ok and numbers_ok and mentions_ok,
        "called": sorted(called),
        "n_calls": len(answer.calls),
        "causal": causal,
        "irrelevant_caveats": irrelevant,
        "input_tokens": answer.input_tokens,
        "output_tokens": answer.output_tokens,
        "seconds": round(seconds, 1),
        "error": error,
        "answer": text,
    }


def run_live(
    questions: list[dict], provider: str, model: str, pause: float = 0.0, sleep=time.sleep
) -> dict:
    rows = []
    for index, q in enumerate(questions):
        if index and pause:
            sleep(pause)
        started = time.perf_counter()
        for attempt in (1, 2):
            try:
                answer, error = agent.ask(q["question"], provider=provider, model=model), None
            except agent.ProviderUnavailable as exc:
                if exc.reason == "quota" and attempt == 1:
                    print(
                        f"{q['id']:<42} quota reached, waiting {QUOTA_WAIT:.0f}s and retrying once"
                    )
                    sleep(QUOTA_WAIT)
                    started = time.perf_counter()
                    continue
                if exc.reason in ("quota", "auth"):
                    raise QuotaExhausted(f"{q['id']}: {exc}") from exc
                answer, error = None, f"{type(exc).__name__}: {exc}"[:300]
            except Exception as exc:  # a timeout or a dead server is a failed question
                answer, error = None, f"{type(exc).__name__}: {exc}"[:300]
            break
        result = score(q, answer, error, time.perf_counter() - started)
        rows.append(result)
        print(f"{q['id']:<42} {'PASS' if result['passed'] else 'FAIL'}  {result['seconds']:6.1f}s  tools={result['called']}"
              + (f"  ERROR {error}" if error else ""))  # fmt: skip
    return {"provider": provider, "model": model, "date": date.today().isoformat(), "rows": rows}


def save(run: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    name = f"{run['provider']}__{re.sub(r'[^A-Za-z0-9.]+', '-', run['model'])}.json"
    path = RESULTS / name
    path.write_text(
        json.dumps(run, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def saved_runs() -> list[dict]:
    if not RESULTS.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob("*.json"))]


def summary(run: dict) -> dict:
    rows = run["rows"]
    with_numbers = [r for r in rows if r["has_numbers"]]
    refusals = [r for r in rows if r["category"] == "refusal"]
    answerable = [r for r in rows if r["category"] != "refusal"]
    timed = [r["seconds"] for r in rows if not r["error"]]
    tokens_in = sum(r["input_tokens"] for r in rows)
    tokens_out = sum(r["output_tokens"] for r in rows)
    price = PRICES.get(run["model"])
    if run["provider"] == "ollama":
        cost = "free (local)"
    elif run["provider"] == "gemini":
        cost = "free (Gemini free tier)"
    elif price:
        cost = f"about ${(tokens_in * price[0] + tokens_out * price[1]) / 1e6:.2f}"
    else:
        cost = "unknown price"
    return {
        "passed": sum(r["passed"] for r in rows),
        "n": len(rows),
        "tools": sum(r["tools"] for r in rows),
        "numbers": sum(r["numbers"] for r in with_numbers),
        "n_numbers": len(with_numbers),
        "refusals": sum(r["refusal_ok"] for r in refusals),
        "n_refusals": len(refusals),
        "false_refusals": sum(not r["refusal_ok"] and not r["error"] for r in answerable),
        "mentions": sum(r["mentions"] for r in rows),
        "errors": sum(bool(r["error"]) for r in rows),
        "avg_seconds": sum(timed) / len(timed) if timed else 0.0,
        "max_seconds": max(timed) if timed else 0.0,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": cost,
    }


def write_report(runs: list[dict], offline: dict[str, list[str]]) -> None:
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
        "[ai_analyst.md](ai_analyst.md). The questions and expected answers were fixed before any model "
        "was run and were not changed to suit a model.",
        "",
        "## Question set check (offline, no model call)",
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
    if not runs:
        lines += [
            "**Not run yet.** Switch the analyst on (`ESG_AI_ENABLED=true`; the default provider is a "
            "free local model through Ollama) and run `.\\scripts\\dev.ps1 eval`.",
        ]
    else:
        lines += [
            "How each question is scored: **tool selection** - every expected tool was called (for a "
            "question that must be refused: no tool at all); **numbers** - every expected number is in "
            "the answer within its tolerance (questions that have numbers); **refusal right** - the three "
            "out-of-scope questions are refused, and no answerable question is refused; **mentions** - a "
            "withheld figure is called withheld, the provisional year is called provisional, expected "
            "words appear, there is no causal wording, and no caveat that does not apply (the Disclosure "
            'Quality Score caveat in an answer about another figure, "provisional" for a final year). '
            "A question passes when tools, numbers and mentions all pass.",
            "",
            "| Provider | Model | Passed | Tool selection | Numbers right | Refusals right | Wrongly refused | Mentions | Errors | Avg time per question | Slowest | Cost of the run |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        evaluated = {run["provider"] for run in runs}
        pending = [(p, m, note) for p, (m, note) in PENDING.items() if p not in evaluated]
        for run in runs:
            m = summary(run)
            lines.append(
                f"| {run['provider']} | `{run['model']}` | **{m['passed']} / {m['n']}** | {m['tools']} / {m['n']} | "
                f"{m['numbers']} / {m['n_numbers']} | {m['refusals']} / {m['n_refusals']} | {m['false_refusals']} | "
                f"{m['mentions']} / {m['n']} | {m['errors']} | {m['avg_seconds']:.0f} s | {m['max_seconds']:.0f} s | {m['cost']} |"
            )
        for provider, model, note in pending:
            lines.append(f"| {provider} | `{model}` | {note} |" + " |" * 9)
        mark = {True: "pass", False: "FAIL"}
        for run in runs:
            m = summary(run)
            lines += [
                "",
                f"### {run['provider']} `{run['model']}` ({run['date']})",
                "",
                f"Tokens: {m['tokens_in']:,} in, {m['tokens_out']:,} out.",
                "",
                "| Question | Category | Tools | Numbers | Mentions | Time | Tools called |",
                "|---|---|---|---|---|---|---|",
            ]
            for r in run["rows"]:
                lines.append(
                    f"| `{r['id']}` | {r['category']} | {mark[r['tools']]} | {mark[r['numbers']]} | "
                    f"{mark[r['mentions']]} | {r['seconds']:.0f} s | {', '.join(r['called']) or '-'} |"
                )
            failed = [r for r in run["rows"] if not r["passed"]]
            if failed:
                lines += ["", "Answers that failed (first 400 characters):", ""]
                for r in failed:
                    short = (r["error"] or r["answer"]).replace("\n", " ").replace("|", "/")[:400]
                    extra = f" (causal wording: {', '.join(r['causal'])})" if r["causal"] else ""
                    if r.get("irrelevant_caveats"):
                        extra += (
                            f" (caveat that does not apply: {', '.join(r['irrelevant_caveats'])})"
                        )
                    lines.append(f"- `{r['id']}`{extra}: {short or '(empty answer)'}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="check the question set only")
    parser.add_argument(
        "--report-only", action="store_true", help="rebuild the report from saved runs"
    )
    parser.add_argument(
        "--no-report", action="store_true", help="do not rewrite docs/ai_analyst_eval.md"
    )
    parser.add_argument(
        "--provider", choices=["ollama", "gemini", "anthropic"], help="override ESG_AI_PROVIDER"
    )
    parser.add_argument("--model", help="override ESG_AI_MODEL")
    parser.add_argument(
        "--pause",
        type=float,
        help=f"seconds between questions (default {GEMINI_PAUSE:.0f} for gemini, else 0)",
    )
    args = parser.parse_args(argv)
    if args.provider:
        os.environ["ESG_AI_PROVIDER"] = args.provider
    if args.model:
        os.environ["ESG_AI_MODEL"] = args.model

    questions = load()
    offline = {q["id"]: check_offline(q) for q in questions}
    for qid, problems in offline.items():
        print(f"{qid:<42} {'ok' if not problems else '; '.join(problems)}")
    run = None
    if not (args.offline or args.report_only):
        if agent.is_enabled():
            provider = agent.provider_name()
            pause = (
                args.pause
                if args.pause is not None
                else (GEMINI_PAUSE if provider == "gemini" else 0.0)
            )
            try:
                run = run_live(questions, provider, agent.model_name(), pause)
            except QuotaExhausted as error:
                print(f"STOPPED, nothing saved - the provider's quota or key failed: {error}")
                return 1
            print(f"saved {save(run).relative_to(ROOT)}")
        else:
            print(f"AI analyst switched off ({agent.disabled_reason()}): live evaluation not run")
    if not args.no_report:
        write_report(saved_runs(), offline)
        print(f"written {REPORT.relative_to(ROOT)}")
    consistent = not any(offline.values())
    return 0 if consistent and (run is None or all(r["passed"] for r in run["rows"])) else 1


if __name__ == "__main__":
    sys.exit(main())
