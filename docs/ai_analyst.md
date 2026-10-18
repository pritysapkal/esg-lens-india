# Ask the data: guided questions and the AI analyst

Week 13. The "Ask the data" page answers questions about the public tables in two ways. Both use
the **same six validated tools** ([`app/ai_analyst/tools.py`](../app/ai_analyst/tools.py)); there is
no other query path. Evaluation: [ai_analyst_eval.md](ai_analyst_eval.md).

| Mode | What it is | Where it runs | Cost |
|---|---|---|---|
| **Guided questions** (default) | A question builder with dropdowns; no language model | everywhere, including the public site | free |
| **AI analyst** | A language model picks the tools for a question typed in your own words | only on a computer where it is switched on - **never in the public deployment** | free with the local model (Ollama), or paid per question with Claude |

## Guided questions (no language model)

[`app/guided.py`](../app/guided.py). The reader picks one of six question types and its details;
each type is exactly one call of one tool, through `tools.call`, so the same validation applies
(a value the tools do not accept is refused). The dropdowns offer only the values the tools
accept, read from the tools themselves. The answer is a sentence, a table with reader-facing
column names, the tool's notes (withheld, provisional, how a figure is built), and the query
itself, so a reader can see exactly what was asked.

| Question type | Tool | The reader picks |
|---|---|---|
| How does a group of companies compare on a figure? | `group_metric` | figure (18 published group metrics), group type, group, year or all years |
| What does one company's report card say? | `company_card` | company, year |
| Where does a company rank among its peers? | `company_percentiles` | company, year, one KPI or all 19 (grouped Environment / Social / Governance) |
| How concentrated are emissions? | `concentration` | year, how many of the largest emitters to list |
| Who changed most on carbon intensity (confirmed changes only)? | `top_movers_confirmed` | improvements or deteriorations, ranking group, how many |
| How often are figures restated in the next report? | `restatement_summary` | all figures, by peer group, or by metric |

One rule is added on display: the restatement summary holds peer groups of 3 and 4 companies,
and guided mode shows their shares as *n<5 (withheld)*, the same 5-company rule as every other
group statistic of the project. `tests/test_guided.py` checks that every question type goes
through `tools.call` and nothing else (a spy on the call, and a static check of the module), that
every combination of the group question runs, and that no table shows a raw column name.

## The AI analyst

```
question --> language model (system prompt + 6 tool definitions)
               |  asks for a tool, e.g. concentration(year="FY2024-25", top_n=5)
               v
             app/ai_analyst/tools.py: validate the arguments, run a fixed query on a public table
               |  result (JSON) back to the model
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
the model instead of running anything. There is no free-form SQL anywhere.

### Two providers, one loop

[`app/ai_analyst/providers.py`](../app/ai_analyst/providers.py). The loop, the tools, the system
prompt, the guardrails, the limits and the refusal handling are the same for both; only the
transport differs.

| | `ollama` (default) | `anthropic` |
|---|---|---|
| Model | `qwen2.5:3b` on this laptop | `claude-haiku-4-5` |
| Cost | free | about 1 US cent per question (see Cost) |
| Key | none | `ANTHROPIC_API_KEY` |
| Network | only `localhost` (Ollama's server) | the Anthropic API |
| Tool format | Ollama function tools (the same JSON schema) | Anthropic tools, `strict` |
| Stop tool calls at the limit | tools are no longer offered (Ollama has no `tool_choice`) | `tool_choice: none` |
| Request timeout | 180 s (a small model on a laptop CPU is slow) | 30 s, 1 retry |
| Refusal | the model's own out-of-scope refusal only | also the API's safety refusal, shown as such, never retried on another model |

### Local model: what this laptop can run

Checked on 2026-10-19: 15.7 GB RAM, of which only about 2 to 3 GB free with the usual apps open
(browser, editor, Docker Desktop when running); 12th-gen Intel Core i5-12450H (8 cores); no
discrete GPU, so the model runs on the CPU. That rules out models of 7B and more (4.5 GB and up)
and leaves the 3B class, about 2 GB at 4-bit quantisation.

| Model (Ollama tag) | Size | Tool calling (`ollama show`: Capabilities) | Licence | Eval (20 questions) |
|---|---|---|---|---|
| **`qwen2.5:3b`** (default) | 1.9 GB, Q4_K_M, 32K context | yes (`tools`) | Qwen Research License: research and non-commercial use | **13 / 20** passed; 3 / 3 refusals right; about 20 s per question |
| `llama3.2:3b` | 2.0 GB, Q4_K_M, 128K context | yes (`tools`) | Llama 3.2 Community License (commercial use allowed within its terms) | 8 / 20 passed; 0 / 3 refusals right; about 60 s per question |

**Chosen: `qwen2.5:3b`.** It fits in the memory this laptop has free, lists tool calling, and in
the evaluation it chose the right tool 19 times in 20, refused all three out-of-scope questions
and answered three times faster than `llama3.2:3b`, which called tools for a forecast and for a
filed-tonnes question it should have refused. Note its licence: the 3B Qwen model is for research
and non-commercial use, which fits this portfolio project; for anything commercial use
`llama3.2:3b` (weaker here) or a larger model. Both were downloaded and run on 2026-10-19.

Install once (Windows): `winget install -e --id Ollama.Ollama`, then `ollama pull qwen2.5:3b`
(about 2 GB). Ollama runs a local server on `http://127.0.0.1:11434`; nothing leaves the laptop.
Close memory-heavy apps (or stop Docker Desktop) before a long session: with less than about
3 GB free, Windows pages and answers slow down sharply.

### Configuration

Read only from environment variables or Streamlit secrets (`agent.setting`): no file of the
project, no `.env` loading in the app, no credential profile. A key is passed to the SDK
explicitly, so it never falls back to another credential source.

| Variable | Default | |
|---|---|---|
| `ESG_AI_ENABLED` | off | must be `true` for either provider (any other value, or unset, keeps the analyst off) |
| `ESG_AI_PROVIDER` | `ollama` | `ollama` or `anthropic`; anything else keeps the analyst off |
| `ESG_AI_MODEL` | `qwen2.5:3b` / `claude-haiku-4-5` | any model the provider has |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | ollama only |
| `ANTHROPIC_API_KEY` | - | anthropic only, required |
| `ESG_AI_EFFORT` | not sent | anthropic only; `low`, `medium` or `high`, for models that accept it (`claude-haiku-4-5` does not) |

Local use, PowerShell, free model: `$env:ESG_AI_ENABLED = 'true'`, then `.\scripts\dev.ps1 app`.
With Claude instead: also `$env:ESG_AI_PROVIDER = 'anthropic'; $env:ANTHROPIC_API_KEY = '...'`.
Secrets can also go in `.streamlit/secrets.toml`, which git ignores (a test fails if it, `.env` or
anything key-like is ever tracked).

**Visitors of the public site never see setup details.** With the analyst off, the page shows the
guided questions and a short note that free-text questions are not available on the public site
and that a demonstration is in the project video.

**A refusal stays a refusal.** If Claude's safety classifier declines a request
(`stop_reason: "refusal"`), the analyst does not retry it on another model: it stops and shows
the user a warning that the model declined. Questions outside the data are refused by the
analyst itself, with either provider (see Guardrails).

## Limits

Hard limits in `agent.LIMITS`, checked by tests:

| Limit | Value | What happens at the limit |
|---|---|---|
| Questions per browser session | 10 | the input box disappears; reload the page for a new session |
| Tool calls per question | 4 | further calls are not run (the model gets an error result) and the next request forbids tools (`tool_choice: none`), so the model must answer with what it has |
| Model requests per question | 5 (4 tool rounds + the answer) | the loop stops with "ask a narrower question" |
| Output tokens per response | 1,500 | the answer is cut and marked as cut |
| Question length | 500 characters | the question is not sent |
| Request timeout | Claude: 30 seconds, 1 retry (connection errors, 429, 5xx only); local model: 180 seconds | the page says the analyst could not answer; the rest of the app is unaffected |
| Local context window | 8,192 tokens (`num_ctx`) | Ollama's own default is smaller and cuts a long prompt silently; the prompt with the six tools is about 3,000 tokens |

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

- `tests/test_guided.py` (CI): one question type per tool; every type goes through `tools.call`
  and nothing else; the dropdowns offer exactly the values the tools accept; withheld,
  provisional and not-ranked answers say so; every combination of the group question runs;
  no table shows a raw column name.
- `tests/test_ai_analyst.py` (CI, no model call): the tool set is fixed and strict; 13 kinds of
  bad arguments are refused before any query; every tool returns derived values only, with its
  source and notes; the loop - with a fake Anthropic client - runs tools, returns errors to the
  model, sends the system prompt and tools; off unless switched on with what the provider needs;
  settings come only from the environment or Streamlit secrets; every limit holds; a refusal is
  one request and is shown, never retried; no fallback anywhere in the app.
- `tests/test_ai_providers.py` (CI, no model, no network): the same loop with a fake Ollama
  client - the same system prompt and tools in Ollama's format, the output cap and the context
  window sent, tool results returned as `tool` messages, bad arguments and unknown tools sent
  back as errors, arguments given as a JSON string parsed, tools withdrawn at the call limit, a
  runaway model cut off, out-of-scope refusals, the local host and timeout passed to the client.
- `tests/test_app.py`: every page and every guided question runs and opens only the public files;
  visitors get the guided questions and a note with no setup details; no input box after 10
  questions.
- `tests/test_repo_safety.py`: no tracked file holds anything key-like; `.env` and
  `.streamlit/secrets.toml` are ignored and untracked.
- [evals/ai_analyst_questions.yaml](../evals/ai_analyst_questions.yaml): 20 questions - 11 plain,
  2 on provisional data, 3 on withheld figures, 1 on a KPI that is not ranked, 3 that must be
  refused - each with the tools it needs, the calls that answer it and the expected numbers, taken
  from the public tables. Offline, every expected call is run and must return the expected
  numbers; a test does this, so the set cannot drift from the data.
- `.\scripts\dev.ps1 eval` asks the model every question and scores tool selection, numeric
  accuracy (with a tolerance per number), refusals and mentions (withheld, provisional, no causal
  wording); each run is saved under `evals/results/` and [ai_analyst_eval.md](ai_analyst_eval.md)
  shows them all.

### Evaluation results (local models, 2026-10-19)

| Model | Passed | Right tool | Numbers right | Refusals right | Wrongly refused | Time per question |
|---|---|---|---|---|---|---|
| `qwen2.5:3b` | 13 / 20 | 19 / 20 | 8 / 13 | 3 / 3 | 1 | median 19 s (the first, which loads the model, 90 s) |
| `llama3.2:3b` | 8 / 20 | 15 / 20 | 5 / 13 | 0 / 3 | 6 | median 59 s |

**What this means, plainly.** The small local model is good at choosing a tool and at refusing
what is out of scope, and not reliable with the numbers: in about one answer in three a figure is
wrong or missing. The failures seen with `qwen2.5:3b`:

- passing a group name as the group type (`group_type="Asset-heavy"`); the tool refused the call,
  as designed, and the model then gave up instead of correcting itself (2 questions);
- a number that is not in the tool result ("10 companies" for 80% of emissions, where the tool
  said 4) and a figure read from the wrong row (the all-companies renewable share given for IT
  services; the all-years restatement share given for FY2022-23) (3 questions);
- one answerable question refused, and one company rank given without its group size.

The guardrails did their part: no invalid call reached the data, nothing outside the public
tables was used, and every number shown under an answer is the true tool result - which is how a
reader can catch the slips above. The questions and expected answers were not changed after the
runs. Treat the local model as a demonstration of the architecture, not as a source of numbers:
for numbers, the guided questions (same tools, no model) are exact. A larger model would do
better; the Claude provider is wired and tested but was not evaluated here (no key on this
machine).

## Cost

**Guided questions and the local model cost nothing** beyond electricity: the local model
runs on this laptop and sends nothing out. The rest of this section is about the Claude provider.

Default Claude model `claude-haiku-4-5`, list price $1 / $5 per million input / output tokens
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
- **The free local model gets about a third of the numeric answers wrong** (evaluation above).
  Every answer shows its tool calls and their numbers so a reader can check, but the guided
  questions are the reliable way to get a figure.
- The local model needs about 2 GB of free memory and a minute or so for the first question
  (loading); on a busy laptop Windows pages and answers slow down sharply.
- The Claude provider has not been evaluated live (no key on this machine).
- The limits apply per browser session; someone who reloads the page gets a new session - one
  more reason the public deployment keeps the analyst off.
