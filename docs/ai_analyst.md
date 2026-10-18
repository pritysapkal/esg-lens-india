# AI analyst

Week 13. A question box in the report card ("Ask the data") that answers in plain English from
the public tables. Code in [`app/ai_analyst/`](../app/ai_analyst/); evaluation in
[ai_analyst_eval.md](ai_analyst_eval.md).

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

A manual tool-use loop (`agent.ask`), at most 8 turns. The model never sees a database or
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

**Configuration.**

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | - | required; without it the page says "disabled" and the rest of the app works |
| `ESG_AI_MODEL` | `claude-opus-5-5` | any current model id, e.g. `claude-sonnet-5-5` |
| `ESG_AI_EFFORT` | `medium` | `low`, `medium` or `high` |

On models that support it (Opus 5.5, Sonnet 5.5, Opus 5, Fable 5.1) the request also opts into
the API's server-side **refusal fallback** (`fallbacks: "default"`): if a safety classifier
declines a request, the API retries it on a fallback model within the same call. Remove it in
`agent._request` if you do not want it. A request that is still declined ends with "The model
declined to answer this question."

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
  client - runs tools, returns errors to the model, handles a refusal and a runaway loop, and sends
  the system prompt and tools; the evaluation set is consistent with the data.
- [evals/ai_analyst_questions.yaml](../evals/ai_analyst_questions.yaml): 20 questions - 11 plain,
  2 on provisional data, 3 on withheld figures, 1 on a KPI that is not ranked, 3 that must be
  refused - each with the tools it needs, the calls that answer it and the expected numbers, taken
  from the public tables. Offline, every expected call is run and must return the expected
  numbers; a test does this, so the set cannot drift from the data.
- `.\scripts\dev.ps1 eval` (needs a key) asks the model every question and scores tool selection,
  numeric accuracy (with a tolerance per number) and mentions (withheld, provisional, refusal,
  no causal wording); it writes [ai_analyst_eval.md](ai_analyst_eval.md).

## Cost

A typical question takes two or three model calls (one or two tool calls, then the answer) with
about 6,000 to 10,000 input tokens in all - mostly the system prompt and the tool definitions,
sent on every call - and a few hundred output tokens. At the list prices of 2026-10 that is
roughly 4 to 6 US cents per question on `claude-opus-5-5` ($4 / $20 per million input / output
tokens) and about half that on `claude-sonnet-5-5` ($2 / $10). The 20-question evaluation costs
about one US dollar on Opus 5.5. These are estimates from the prompt size, not measured: the
evaluation report records the real token counts when it runs. Prompt caching of the system prompt
and tools would cut the input cost of follow-up calls; it is not switched on yet.

## Limitations

- The analyst knows only what the seven public tables hold - no filed values, no statistics
  results, no balanced-panel figures.
- One question at a time: earlier questions on the page are shown but not sent back to the model.
- The live evaluation has not been run yet (no key on this machine): see
  [ai_analyst_eval.md](ai_analyst_eval.md).
