# AI analyst

Week 13. A question box in the report card ("Ask the data") that answers in plain English from
the public tables. Code in [`app/ai_analyst/`](../app/ai_analyst/); evaluation in
[ai_analyst_eval.md](ai_analyst_eval.md).

**It is off by default, and off in the public deployment.** It runs only when `ESG_AI_ENABLED=true`
**and** `ANTHROPIC_API_KEY` are both set. The Streamlit Community Cloud deployment runs with it
off; the AI demo is shown in the project video instead. Locally it runs within hard limits (see
"Limits") so that a session cannot run up a bill.

## How it works

```
question --> Claude (system prompt + 6 tool definitions)
               |  asks for a tool, e.g. concentration(year="FY2024-25", top_n=5)
               v
             app/ai_analyst/tools.py: validate the arguments, run a fixed query on a public table
               |  result (JSON) back to Claude
               v
             answer in plain English  +  every tool call and its numbers shown under the answer
```

A manual tool-use loop (`agent.ask`) within the limits below. The model never sees a database or
writes a query; it can only ask for one of six tools, and every tool reads one of the seven
public tables through `app/data.py`, the same door the rest of the app uses.

| Tool | Arguments (allowed values only) | Answers |
|---|---|---|
| `group_metric` | metric (18 published group metrics), group type, group, year | a group figure, or its status: *n<5 (withheld)*, *not yet observable* |
| `company_card` | company (51 names or NSE symbols), year | Disclosure Quality Score, grade, rank, percentile, reasons points were lost, assurance, computed intensities, provisional flag |
| `company_percentiles` | company, year, KPI (optional) | percentile and rank in the ranking group for each KPI, with the ranking status |
| `concentration` | year, top_n (1-20) | top 1 / 5 / 10 shares, companies for 80%, the largest emitters' shares |
| `top_movers_confirmed` | direction, ranking group (optional), limit (1-10) | largest confirmed year-on-year changes in GHG intensity, and how many were set aside and why |
| `restatement_summary` | level, group (optional) | how often figures were restated materially and how many flatter the trend |

**Validation.** Allowed values are read from the public tables, so the schemas always match the
data. Tools are declared `strict` (no extra or missing fields), and `tools.call` checks every
value again before a query runs: an unknown tool, an unknown argument, a metric that is not
public, a company or year that is not covered, a number out of range - each returns an error to
the model (`is_error`) instead of running anything. There is no free-form SQL anywhere.

**Configuration.** Read only from environment variables or Streamlit secrets
(`agent.setting`): no file of the project, no `.env` loading in the app, no credential profile.
The key is passed to the SDK explicitly, so it never falls back to another credential source.

| Variable | Default | |
|---|---|---|
| `ESG_AI_ENABLED` | off | must be `true` (any other value, or unset, keeps the analyst off) |
| `ANTHROPIC_API_KEY` | - | required as well; without it the page says why the analyst is off |
| `ESG_AI_MODEL` | `claude-haiku-4-5` | any model id, e.g. `claude-sonnet-5-5` for harder questions |
| `ESG_AI_EFFORT` | not sent | `low`, `medium` or `high`, only for models that accept it (`claude-haiku-4-5` does not) |

Local use, PowerShell: `$env:ESG_AI_ENABLED = 'true'; $env:ANTHROPIC_API_KEY = '...'` in the
session, then `.\scripts\dev.ps1 app`. Or put both in `.streamlit/secrets.toml`, which git ignores
(a test fails if it, `.env` or anything key-like is ever tracked).

**A refusal stays a refusal.** If the model's safety classifier declines a request
(`stop_reason: "refusal"`), the analyst does not retry it on another model: it stops and shows
the user a warning that the model declined, with the category in the answer record. Questions
outside the data are refused by the analyst itself (see Guardrails).

## Limits

Hard limits in `agent.LIMITS`, checked by tests:

| Limit | Value | What happens at the limit |
|---|---|---|
| Questions per browser session | 10 | the input box disappears; reload the page for a new session |
| Tool calls per question | 4 | further calls are not run (the model gets an error result) and the next request forbids tools (`tool_choice: none`), so the model must answer with what it has |
| Model requests per question | 5 (4 tool rounds + the answer) | the loop stops with "ask a narrower question" |
| Output tokens per response | 1,500 | the answer is cut and marked as cut |
| Question length | 500 characters | the question is not sent |
| Request timeout | 30 seconds, 1 retry (connection errors, 429, 5xx only) | the page says the analyst could not answer; the rest of the app is unaffected |

So one question costs at most 5 requests and 7,500 output tokens, and one session at most 50
requests.

## Guardrails

Written into the system prompt (`agent.SYSTEM_PROMPT`) and checked by tests and the evaluation:

- **Numbers only from tools.** Every number must come from a tool result of the conversation, with
  the table it came from. Filed absolute values (tonnes, energy, water, turnover, headcount) do
  not exist in the tools and must not be guessed.
- **No home-made group figures.** Group figures come from `group_metric`; never an average of
  company intensities.
- **Say how far a number can be trusted.** Withheld figures are reported as withheld (fewer than
  5 companies); FY2025-26 is called provisional; unconfirmed year-on-year moves are not ranked.
  The tools put these labels into their results, so the model has them in front of it.
- **Associations, not causes.** The prompt forbids "causes", "drives", "leads to", "results in";
  the evaluation fails an answer that uses causal wording.
- **Out of scope -> refuse.** Share prices, forecasts, investment advice, companies or years not
  covered, filed values: no tool call, and the answer starts with "I can't answer that from the
  ESG Lens India public data", followed by what it can answer.
- **Transparency.** The page shows every tool call, its arguments and the rows it returned under
  the answer, so a reader can check each number.
- The Disclosure Quality Score is described as disclosure quality, not an ESG rating; nothing is
  investment advice.

What the guardrails cannot do: a language model can still misread a table or phrase something
loosely. That is why the numbers are shown next to the answer, and why the evaluation exists.

## Tests and evaluation

- `tests/test_ai_analyst.py` (runs in CI, no API call): the tool set is fixed and strict; 13 kinds
  of bad arguments are refused before any query; every tool returns derived values only, with its
  source and notes; withheld and provisional figures come back labelled; the loop - with a fake
  client - runs tools, returns errors to the model, sends the system prompt and tools; the
  analyst is off unless both switches are set; settings come only from the environment or
  Streamlit secrets; every limit holds (tool calls, requests, output tokens, question length,
  questions per session, timeout and retries passed to the client); a refusal is one request and
  is shown, never retried; no fallback anywhere in the app; the evaluation set is consistent
  with the data.
- `tests/test_app.py`: the page says why the analyst is off (a key alone is not enough) and
  offers no input after 10 questions.
- `tests/test_repo_safety.py`: no tracked file holds anything key-like; `.env` and
  `.streamlit/secrets.toml` are ignored and untracked.
- [evals/ai_analyst_questions.yaml](../evals/ai_analyst_questions.yaml): 20 questions - 11 plain,
  2 on provisional data, 3 on withheld figures, 1 on a KPI that is not ranked, 3 that must be
  refused - each with the tools it needs, the calls that answer it and the expected numbers, taken
  from the public tables. Offline, every expected call is run and must return the expected
  numbers; a test does this, so the set cannot drift from the data.
- `.\scripts\dev.ps1 eval` (needs a key) asks the model every question and scores tool selection,
  numeric accuracy (with a tolerance per number) and mentions (withheld, provisional, refusal,
  no causal wording); it writes [ai_analyst_eval.md](ai_analyst_eval.md).

## Cost

Default model `claude-haiku-4-5`, list price $1 / $5 per million input / output tokens
(2026-10). A typical question takes two or three requests (one or two tool calls, then the
answer) with about 6,000 to 10,000 input tokens in all - mostly the system prompt and the tool
definitions, sent with every request - and a few hundred output tokens: **about 1 US cent per
question**, about 10 cents for a full session of 10 questions. The limits cap the worst case at
roughly 6 cents per question (5 requests, 7,500 output tokens) and 60 cents per session. The
20-question evaluation costs about 20 cents. On `claude-sonnet-5-5` ($2 / $10) multiply by about
two.

These are estimates from the prompt size, not measurements: the evaluation report records the
real token counts when it runs. Prompt caching of the system prompt and tools would cut the
input cost of follow-up requests; it is not switched on.

## Limitations

- The analyst knows only what the seven public tables hold - no filed values, no statistics
  results, no balanced-panel figures.
- One question at a time: earlier questions on the page are shown but not sent back to the model.
- The live evaluation has not been run yet (no key on this machine): see
  [ai_analyst_eval.md](ai_analyst_eval.md). The limits apply per browser session; someone who
  reloads the page gets a new session - which is one reason the public deployment keeps the
  analyst off.
- `claude-haiku-4-5` is the cheapest choice that is well tested here, not the strongest; the
  evaluation is the place to compare it with a larger model before relying on its answers.
