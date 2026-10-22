"""Evaluate the AI analyst against evals/ai_analyst_questions.yaml and write docs/ai_analyst_eval.md.

    python scripts/eval_ai_analyst.py                    # live, with the configured provider
    python scripts/eval_ai_analyst.py --provider ollama --model qwen2.5:3b
    python scripts/eval_ai_analyst.py --provider gemini         # free tier; paced (--pause)
    python scripts/eval_ai_analyst.py --offline          # no model call: checks the question set
    python scripts/eval_ai_analyst.py --report-only      # rebuild the report from saved results
    python scripts/eval_ai_analyst.py --provider gemini --only q02 q03   # re-run some questions,
                                                         # merged into the saved run

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
A question passes when all three pass.

Not scored: a question the provider could not answer at all - a server error (5xx) or a timeout,
after agent.ask's own retry and one more retry of the whole question here - is an outage, not a
model failure. It is reported as "not scored", and the pass rate is given both over all questions
and over the answered ones. Re-run just those questions with --only. A re-run counts only for a
question that was NOT scored (an outage): it replaces that row. A question that already has a
scored answer keeps its first scored answer as the official result; the re-run is saved in the
run's "variability" list and reported as run-to-run variability, never as a replacement.

Offline mode runs each expected tool call and checks that the expected numbers and statuses are
what the tools return today.
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
from statistics import median

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai_analyst import agent, providers, tools  # noqa: E402

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
SERVER_ERROR_WAIT = 20.0  # seconds before the one retry of a question that hit a 5xx or timeout
# a provider outage in a run saved before rows recorded "not_scored"
MENTION_GAP = 2  # words allowed between the words of a required phrase (see mentioned)
OUTAGE = re.compile(r"ServerError|\b5\d\d\b|timed? ?out|timeout", re.I)


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


def mentioned(phrase: str, text: str, strict: bool = False) -> bool:
    """A required phrase appears in the answer. Its words must come in order, in one clause, with
    at most MENTION_GAP other words between two of them, so a clear equivalent counts: "not
    material" matches "not considered material" and "not material for this group". strict=True
    is the exact-phrase rule used before 2026-10-22 (kept to report the change)."""
    if strict:
        return phrase.casefold() in text.casefold()
    gap = rf"(?:\s+[\w'-]+){{0,{MENTION_GAP}}}\s+"
    pattern = r"\b" + gap.join(re.escape(word) for word in phrase.split()) + r"\b"
    return bool(re.search(pattern, text, re.I))


def judge_mentions(
    question: dict, text: str, refusal_ok: bool, strict: bool = False
) -> tuple[bool, list[str], list[str]]:
    """(mentions passed, causal words, caveats that do not apply) for one answer. Used for live
    answers and for re-scoring saved ones, so both follow the same rules."""
    causal = CAUSAL.findall(text)
    if question["category"] == "refusal":
        return refusal_ok and not causal, causal, []
    ok = refusal_ok and all(mentioned(p, text, strict) for p in question.get("expected_text", []))
    if question["category"] == "suppressed":
        ok = ok and bool(WITHHELD.search(text))
    if question["category"] == "provisional":
        ok = ok and "provisional" in text.lower()
    irrelevant = irrelevant_caveats(question, text)
    return ok and not causal and not irrelevant, causal, irrelevant


def score(
    question: dict,
    answer: agent.Answer | None,
    error: str | None = None,
    seconds: float = 0.0,
    not_scored: bool = False,
) -> dict:
    """One question. An error never crashes the run: a provider outage (5xx, timeout) is marked
    not_scored, any other error counts as a failure."""
    if answer is None:
        answer = agent.Answer(text="")
    called = {call.name for call in answer.calls}
    text = answer.text
    refusal = question["category"] == "refusal"
    if refusal:
        tools_ok = not answer.calls
        refusal_ok = answer.refused and not answer.calls
    else:
        tools_ok = set(question["expected_tools"]) <= called
        refusal_ok = not answer.refused  # a question it should answer must not be refused
    numbers = numbers_in(text)
    numbers_ok = all(found(e, numbers) for e in question["expected_numbers"])
    mentions_ok, causal, irrelevant = judge_mentions(question, text, refusal_ok)
    if error:
        tools_ok = numbers_ok = mentions_ok = refusal_ok = False
    return {
        "id": question["id"],
        "category": question["category"],
        "has_numbers": bool(question["expected_numbers"]),
        "not_scored": bool(error) and not_scored,
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
        # what the model asked for, so a wrong row or argument can be told from a wrong reading
        "calls": [
            {"name": c.name, "arguments": c.arguments, "error": c.error} for c in answer.calls
        ],
        "date": date.today().isoformat(),
    }


def is_not_scored(row: dict) -> bool:
    """A provider outage: the question was never answered, so it says nothing about the model."""
    if "not_scored" in row:
        return bool(row["not_scored"])
    return bool(row.get("error")) and bool(OUTAGE.search(row["error"]))


def rescored(row: dict, question: dict | None, strict: bool = False) -> dict:
    """A saved row under today's mention rules, judged again from its saved answer: no model
    call. Tools, numbers and refusals are kept as saved; an outage stays not scored."""
    row = dict(row, not_scored=is_not_scored(row))
    row.setdefault("irrelevant_caveats", [])
    if question is None or row["not_scored"] or row["error"]:
        return row
    ok, causal, irrelevant = judge_mentions(question, row["answer"], row["refusal_ok"], strict)
    return dict(row, mentions=ok, causal=causal, irrelevant_caveats=irrelevant,
                passed=row["tools"] and row["numbers"] and ok)  # fmt: skip


def run_live(
    questions: list[dict], provider: str, model: str, pause: float = 0.0, sleep=time.sleep
) -> dict:
    rows = []
    for index, q in enumerate(questions):
        if index and pause:
            sleep(pause)
        started = time.perf_counter()
        for attempt in (1, 2):
            outage = False
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
                outage = providers.is_transient(exc)
            except Exception as exc:  # a timeout or a dead server: never a crash of the run
                answer, error = None, f"{type(exc).__name__}: {exc}"[:300]
                outage = providers.is_transient(exc)
            if outage and attempt == 1:
                print(f"{q['id']:<42} {error}; waiting {SERVER_ERROR_WAIT:.0f}s, retrying once")
                sleep(SERVER_ERROR_WAIT)
                started = time.perf_counter()
                continue
            break
        result = score(q, answer, error, time.perf_counter() - started, not_scored=outage)
        rows.append(result)
        verdict = "NOT SCORED" if result["not_scored"] else "PASS" if result["passed"] else "FAIL"
        print(f"{q['id']:<42} {verdict}  {result['seconds']:6.1f}s  tools={result['called']}"
              + (f"  ERROR {error}" if error else ""))  # fmt: skip
    return {"provider": provider, "model": model, "date": date.today().isoformat(), "rows": rows}


def result_path(provider: str, model: str) -> Path:
    return RESULTS / f"{provider}__{re.sub(r'[^A-Za-z0-9.]+', '-', model)}.json"


def _named(question: dict, name: str) -> bool:
    return name in (question["id"], question["id"].split("_")[0])


def select(questions: list[dict], only: list[str]) -> list[dict]:
    """The questions --only names: a full id or its number (q02 = q02_companies_for_80)."""
    unknown = [name for name in only if not any(_named(q, name) for q in questions)]
    if unknown:
        raise SystemExit(f"--only: no question {', '.join(unknown)}")
    return [q for q in questions if any(_named(q, name) for name in only)]


def load_run(provider: str, model: str) -> dict | None:
    path = result_path(provider, model)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def merge(previous: dict | None, run: dict, questions: list[dict]) -> dict:
    """Re-run rows merged into the saved run, in the order of the question set. A re-run counts
    only for a question that was not scored (a provider outage): it replaces that row. For a
    question that already has a scored answer, the first scored answer stays official and the
    re-run goes to the run's "variability" list (an outage on a re-run is not recorded)."""
    rows = {r["id"]: r for r in (previous or {}).get("rows", [])}
    variability = list((previous or {}).get("variability", []))
    for row in run["rows"]:
        saved = rows.get(row["id"])
        if saved is None or is_not_scored(saved):
            rows[row["id"]] = row
        elif not is_not_scored(row):
            variability.append(row)
    order = {q["id"]: i for i, q in enumerate(questions)}
    merged = dict(run, rows=sorted(rows.values(), key=lambda r: order.get(r["id"], len(order))))
    if variability:
        merged["variability"] = variability
    return merged


def save(run: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = result_path(run["provider"], run["model"])
    path.write_text(
        json.dumps(run, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def saved_runs() -> list[dict]:
    if not RESULTS.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob("*.json"))]


def summary(run: dict, questions: list[dict] | None = None, strict: bool = False) -> dict:
    """The rates of one run. Not-scored questions (provider outages) count in "of all" and are
    left out of every other rate, which is over the answered questions."""
    by_id = {q["id"]: q for q in (questions if questions is not None else load())}
    rows = [rescored(r, by_id.get(r["id"]), strict) for r in run["rows"]]
    answered = [r for r in rows if not r["not_scored"]]
    with_numbers = [r for r in answered if r["has_numbers"]]
    refusals = [r for r in answered if r["category"] == "refusal"]
    answerable = [r for r in answered if r["category"] != "refusal"]
    timed = sorted(r["seconds"] for r in answered if not r["error"])
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
    official = {r["id"]: r for r in rows}
    variability = [rescored(r, by_id.get(r["id"]), strict) for r in run.get("variability", [])]
    return {
        "rows": rows,
        "variability": variability,
        "variability_notes": [
            f"{v['id'].split('_')[0]}: re-run {'passed' if v['passed'] else 'failed'}; "
            f"first scored answer ({'pass' if official[v['id']]['passed'] else 'FAIL'}) stays official"
            for v in variability
            if v["id"] in official
        ],
        "passed": sum(r["passed"] for r in answered),
        "n": len(rows),
        "answered": len(answered),
        "not_scored": len(rows) - len(answered),
        "tools": sum(r["tools"] for r in answered),
        "numbers": sum(r["numbers"] for r in with_numbers),
        "n_numbers": len(with_numbers),
        "refusals": sum(r["refusal_ok"] for r in refusals),
        "n_refusals": len(refusals),
        "false_refusals": sum(not r["refusal_ok"] and not r["error"] for r in answerable),
        "caveats": sum(not r["irrelevant_caveats"] for r in answerable),
        "n_caveats": len(answerable),
        "mentions": sum(r["mentions"] for r in answered),
        "errors": sum(bool(r["error"]) for r in answered),
        "median_seconds": median(timed) if timed else 0.0,
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
            "How each question is scored: **right tool** - every expected tool was called (for a "
            "question that must be refused: no tool at all); **numbers right** - every expected number "
            "is in the answer within its tolerance (questions that have numbers); **refusals right** - "
            "the three out-of-scope questions are refused; **wrongly refused** - answerable questions "
            "the model refused; **caveat check** - no caveat that does not apply (the Disclosure "
            'Quality Score caveat in an answer about another figure, "provisional" for a final year); '
            "**mentions** - a withheld figure is called withheld, the provisional year is called "
            "provisional, expected words appear, no causal wording, and the caveat check. A question "
            "passes when right tool, numbers and mentions all pass.",
            "",
            "**Not scored** - the provider could not answer at all (a server error such as HTTP 504, or "
            "a timeout) even after one retry of the request and one retry of the question. That is an "
            "outage, not a model failure, so it is not counted against the model: the pass rate is "
            "given over all questions and over the answered ones, and every other column is over the "
            "answered questions only. Re-run such questions with `--only`: a re-run replaces a row only "
            "if that question was not scored. A question that was already scored keeps its first "
            "scored answer as the official result, and the re-run is reported as **run-to-run "
            "variability** (last column), not counted. Runs saved before the caveat check existed "
            "are re-checked on their saved answers.",
            "",
            "| Provider | Model | Passed (of all) | Passed (of answered) | Not scored | Right tool | Numbers right | Refusals right | Wrongly refused | Caveat check | Median time per question | Cost of the run | Variability |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        evaluated = {run["provider"] for run in runs}
        pending = [(p, m, note) for p, (m, note) in PENDING.items() if p not in evaluated]
        summaries = [(run, summary(run, questions)) for run in runs]
        for run, m in summaries:
            lines.append(
                f"| {run['provider']} | `{run['model']}` | **{m['passed']} / {m['n']}** | "
                f"**{m['passed']} / {m['answered']}** | {m['not_scored']} | {m['tools']} / {m['answered']} | "
                f"{m['numbers']} / {m['n_numbers']} | {m['refusals']} / {m['n_refusals']} | {m['false_refusals']} | "
                f"{m['caveats']} / {m['n_caveats']} | {m['median_seconds']:.0f} s | {m['cost']} | "
                f"{'; '.join(m['variability_notes']) or '-'} |"
            )
        for provider, model, note in pending:
            lines.append(f"| {provider} | `{model}` | {note} |" + " |" * 10)
        lines += [
            "",
            "### Scoring change made after seeing the results (2026-10-22)",
            "",
            "Required words (`expected_text`) were matched as an exact phrase. After the Gemini run, "
            'an answer that said Infosys\'s water intensity is "not considered material" failed for '
            'lack of the words "not material". The rule now accepts the phrase\'s words in order '
            f'with up to {MENTION_GAP} other words between them in one clause ("not considered '
            'material", "not material for this group"). It applies to every provider alike; the '
            "saved answers of all runs were scored again with no new model call. No question, "
            "expected number or expected text was changed.",
            "",
            "| Provider | Model | Passed before (exact phrase) | Passed after | Mentions before | Mentions after | Questions that changed |",
            "|---|---|---|---|---|---|---|",
        ]
        for run, m in summaries:
            before = summary(run, questions, strict=True)
            changed = [
                f"`{a['id']}` ({'pass' if a['passed'] else 'FAIL'})"
                for a, b in zip(m["rows"], before["rows"], strict=True)
                if a["passed"] != b["passed"] or a["mentions"] != b["mentions"]
            ]
            lines.append(
                f"| {run['provider']} | `{run['model']}` | {before['passed']} / {before['n']} | "
                f"{m['passed']} / {m['n']} | {before['mentions']} / {before['answered']} | "
                f"{m['mentions']} / {m['answered']} | {', '.join(changed) or 'none'} |"
            )
        mark = {True: "pass", False: "FAIL"}
        for run, m in summaries:
            lines += [
                "",
                f"### {run['provider']} `{run['model']}` ({run['date']})",
                "",
                f"Tokens: {m['tokens_in']:,} in, {m['tokens_out']:,} out. Slowest answered question: "
                f"{m['max_seconds']:.0f} s.",
                "",
                "| Question | Category | Tools | Numbers | Mentions | Caveats | Time | Tools called |",
                "|---|---|---|---|---|---|---|---|",
            ]
            for r in m["rows"]:
                if r["not_scored"]:
                    cells = "not scored | not scored | not scored | not scored"
                else:
                    caveat = (
                        "-" if r["category"] == "refusal" else mark[not r["irrelevant_caveats"]]
                    )
                    cells = f"{mark[r['tools']]} | {mark[r['numbers']]} | {mark[r['mentions']]} | {caveat}"
                lines.append(
                    f"| `{r['id']}` | {r['category']} | {cells} | {r['seconds']:.0f} s | "
                    f"{', '.join(r['called']) or '-'} |"
                )
            outages = [r for r in m["rows"] if r["not_scored"]]
            if outages:
                listed = ", ".join("`" + r["id"] + "` (" + r["error"] + ")" for r in outages)
                numbers = " ".join(r["id"].split("_")[0] for r in outages)
                lines += [
                    "",
                    f"Not scored (provider outage): {listed}. Re-run them with "
                    f"`python scripts/eval_ai_analyst.py --provider {run['provider']} --only {numbers}`.",
                ]
            if m["variability"]:
                lines += [
                    "",
                    "Run-to-run variability - re-runs of questions that were already scored (the first "
                    "scored answer above stays official; these are not counted):",
                    "",
                ]
                for v in m["variability"]:
                    short = v["answer"].replace("\n", " ").replace("|", "/")[:400]
                    lines.append(
                        f"- `{v['id']}` re-run ({v.get('date', 'undated')}): "
                        f"{'passed' if v['passed'] else 'failed'}. {short}"
                    )
                    for call in v.get("calls", []):
                        args = ", ".join(f"{k}={val!r}" for k, val in call["arguments"].items())
                        result = f" -> error: {call['error']}" if call["error"] else ""
                        lines.append(f"  - `{call['name']}({args})`{result}")
            failed = [r for r in m["rows"] if not r["passed"] and not r["not_scored"]]
            if failed:
                lines += ["", "Answers that failed (first 400 characters):", ""]
                for r in failed:
                    short = (r["error"] or r["answer"]).replace("\n", " ").replace("|", "/")[:400]
                    extra = f" (causal wording: {', '.join(r['causal'])})" if r["causal"] else ""
                    if r["irrelevant_caveats"]:
                        extra += (
                            f" (caveat that does not apply: {', '.join(r['irrelevant_caveats'])})"
                        )
                    lines.append(f"- `{r['id']}`{extra}: {short or '(empty answer)'}")
                    for call in r.get("calls", []):
                        args = ", ".join(f"{k}={v!r}" for k, v in call["arguments"].items())
                        result = f" -> error: {call['error']}" if call["error"] else ""
                        lines.append(f"  - `{call['name']}({args})`{result}")
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
        "--only",
        nargs="+",
        metavar="ID",
        help="run only these questions (full id or number, e.g. q02 q03) and merge them into the "
        "saved run of the same provider and model: a re-run replaces a not-scored (outage) row; a "
        "question that was already scored keeps its first answer and the re-run is saved as a "
        "variability note",
    )
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
            selected = select(questions, args.only) if args.only else questions
            try:
                run = run_live(selected, provider, agent.model_name(), pause)
            except QuotaExhausted as error:
                print(f"STOPPED, nothing saved - the provider's quota or key failed: {error}")
                return 1
            if args.only:
                previous = load_run(provider, run["model"])
                known = len((previous or {}).get("variability", []))
                run = merge(previous, run, questions)
                for v in run.get("variability", [])[known:]:
                    print(
                        f"{v['id']:<42} already scored: kept as run-to-run variability, not counted"
                    )
            path = save(run)
            print(f"saved {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
        else:
            print(f"AI analyst switched off ({agent.disabled_reason()}): live evaluation not run")
    if not args.no_report:
        write_report(saved_runs(), offline)
        print(f"written {REPORT.relative_to(ROOT)}")
    consistent = not any(offline.values())
    return 0 if consistent and (run is None or all(r["passed"] for r in run["rows"])) else 1


if __name__ == "__main__":
    sys.exit(main())
