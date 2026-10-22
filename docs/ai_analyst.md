# Ask the data: guided questions and the AI analyst

Week 13. The "Ask the data" page answers questions about the public tables in two ways. Both use
the **same six validated tools** ([`app/ai_analyst/tools.py`](../app/ai_analyst/tools.py)); there is
no other query path. Evaluation: [ai_analyst_eval.md](ai_analyst_eval.md).

| Mode | What it is | Where it runs | Cost |
|---|---|---|---|
| **Guided questions** (default) | A question builder with dropdowns; no language model | everywhere, including the public site | free |
| **AI analyst** | A language model picks the tools for a question typed in your own words | where it is switched on: locally with any provider; on the public site **only with Gemini's free tier**, behind the per-session limits and a notice to visitors | free with the local model (Ollama) or Gemini's free tier; paid per question with Claude |

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

Withheld figures come from the tables themselves: `rpt_public_group_metrics` and
`rpt_public_restatement_summary` leave a group statistic empty for fewer than 5 companies, the
tools pass that on as *n<5 (withheld)*, and guided mode and the AI analyst show it as such (for
example the restatement shares of the peer groups of 3 and 4 companies). `tests/test_guided.py` checks that every question type goes
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

### Three providers, one loop

[`app/ai_analyst/providers.py`](../app/ai_analyst/providers.py). The loop, the tools, the system
prompt, the guardrails, the limits and the refusal handling are the same for all three; only the
transport differs.

| | `ollama` (default) | `gemini` | `anthropic` |
|---|---|---|---|
| Model | `qwen2.5:3b` on this laptop | `gemini-3.5-flash-lite` | `claude-haiku-4-5` |
| Cost | free | free (Google's free tier; billing must stay off) | about 1 US cent per question (see Cost) |
| Key | none | `GEMINI_API_KEY` | `ANTHROPIC_API_KEY` |
| Network | only `localhost` (Ollama's server) | the Gemini API (Google AI Studio key) | the Anthropic API |
| SDK | `ollama` | Google Gen AI SDK `google-genai` 2.28.0 | `anthropic` |
| Tool format | Ollama function tools (the same JSON schema) | function declarations with the same JSON schema (`parameters_json_schema`); the SDK's automatic function calling is off | Anthropic tools, `strict` |
| Stop tool calls at the limit | tools are no longer offered (Ollama has no `tool_choice`) | function calling mode `NONE` | `tool_choice: none` |
| Request timeout | 180 s (a small model on a laptop CPU is slow) | 30 s | 30 s |
| Retry | one, after 3 s, for a server error (5xx) or a timeout only; never a 429, a key error or a refusal (`agent.respond`; the SDKs' own retries are off) | the same | the same |
| Refusal | the model's own out-of-scope refusal only | also Google's safety stop (finish reason `SAFETY`, `PROHIBITED_CONTENT`, ... or a blocked question), shown as such, never retried | also the API's safety refusal, shown as such, never retried on another model |
| Cannot answer (quota, key, API down) | an error message | `ProviderUnavailable`: the page falls back to the guided questions (below) | an error message |

### Gemini (free tier)

**Model: `gemini-3.5-flash-lite`.** Checked on 2026-10-20 in Google's official documentation:
the [models page](https://ai.google.dev/gemini-api/docs/models) (last updated 2026-10-13) lists
it as a stable model and recommends it, with `gemini-3.8-flash`, for new projects (the 2.0 models
are shut down, and 2.5 is open only to earlier users); its
[model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) (2026-07-30)
lists function calling as supported, with 1,048,576 input and 65,536 output tokens; the
[pricing page](https://ai.google.dev/gemini-api/docs/pricing) (2026-10-16) shows a free tier for
it - input and output "Free of charge", and **"Used to improve our products: Yes"**. A Flash-Lite
model was chosen over `gemini-3.8-flash` because the questions are short tool-routing tasks and
the lighter models have historically had the more generous free-tier quotas. Another model can
be set with `ESG_AI_MODEL`.

**Free-tier rate limits (2026-10-20).** The official
[rate-limits page](https://ai.google.dev/gemini-api/docs/rate-limits) (last updated 2026-10-15)
no longer prints per-model free-tier numbers: it says limits are per project, are measured as
requests per minute (RPM), tokens per minute (TPM) and requests per day (RPD), vary by model and
tier, and are shown for your own project in Google AI Studio; the daily count resets at
midnight Pacific time. **Look up the live numbers for your key in AI Studio** (project ->
rate limits) before a long session. For orientation only: the last published free-tier figures,
for the older `gemini-2.5-flash-lite`, were 15 RPM, 250,000 TPM and 1,000 RPD. With these limits
the analyst uses 2 to 3 requests per question (at most 5), so a few hundred questions a day.

**Get a key (free).** Sign in at [Google AI Studio](https://aistudio.google.com/), choose *Get API
key* -> *Create API key* (it creates or uses a Google Cloud project), and copy the key. Then:

- Put it **only** in your local environment or your local `.env` (git ignores `.env`), or in the
  Streamlit app's *Secrets* for the deployment - **never in code, in `.env.example`, or in any
  tracked file**. A test fails if a Google key (`AIza...`) or a `GEMINI_API_KEY=` value is ever
  tracked, and `.gitignore` also covers Google credential files (`client_secret*.json`,
  service-account JSON, `application_default_credentials.json`).
- **NEVER enable billing on the Google Cloud project that holds this key.** With billing off, the
  key can only use the free tier: when the quota runs out, requests are refused (HTTP 429) and
  nothing is charged. With billing on, the same key would be charged per token, and the public
  site would let anyone spend it. Keep a separate project if you ever need paid use.
- The analyst passes the key to the SDK explicitly with Vertex AI switched off, so the SDK never
  picks up `GOOGLE_API_KEY`, gcloud credentials or a (billed) Cloud project by itself.

**Privacy.** On the free tier Google may use what is sent to improve its products. The page
tells every visitor before they ask: *"Questions are sent to Google's Gemini API; on the free
tier Google may use them to improve its products."* Only the question, the system prompt, the
tool definitions and the tool results (public figures) are sent.

**When Gemini cannot answer, the page falls back to the guided questions.** The guided questions
are the default, sit above the free-text box and never depend on a model, so they always work.

| Situation | What the reader sees | Free-text box |
|---|---|---|
| free-tier quota used up (HTTP 429 `RESOURCE_EXHAUSTED`) | "Free-text questions are paused: the free AI quota is used up for now. The guided questions above answer the same data and always work." | hidden for the rest of the browser session (retrying would only hit the quota again) |
| key missing (`ESG_AI_ENABLED=true` but no `GEMINI_API_KEY`) or rejected (401 / 403 / invalid key) | "Free-text questions are not available right now. The guided questions above ..." | not shown |
| API error, timeout, network (5xx, 30 s) | "The AI analyst could not answer just now (the AI service did not respond). Please try again in a minute. The guided questions above ..." | stays; the failed question is not counted |
| safety stop by Gemini | the usual refusal warning ("The model declined to answer ...") | stays |

No message shows a status code, a variable name or a key; the reason goes to the app log only
(the terminal locally, *Manage app -> Logs* on Community Cloud). The page never crashes on an API
failure, and a failed question is not retried on another model or provider.

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
| `ESG_AI_ENABLED` | off | must be `true` for every provider (any other value, or unset, keeps the analyst off) |
| `ESG_AI_PROVIDER` | `ollama` | `gemini`, `ollama` or `anthropic`; anything else keeps the analyst off |
| `ESG_AI_MODEL` | `qwen2.5:3b` / `gemini-3.5-flash-lite` / `claude-haiku-4-5` | any model the provider has |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | ollama only |
| `GEMINI_API_KEY` | - | gemini only, required (Google AI Studio, free tier; see above) |
| `ANTHROPIC_API_KEY` | - | anthropic only, required |
| `ESG_AI_EFFORT` | not sent | anthropic only; `low`, `medium` or `high`, for models that accept it (`claude-haiku-4-5` does not) |

Local use, PowerShell, free local model: `$env:ESG_AI_ENABLED = 'true'`, then
`.\scripts\dev.ps1 app`. With Gemini: also `$env:ESG_AI_PROVIDER = 'gemini'` and
`$env:GEMINI_API_KEY = '<your key>'`. With Claude: `$env:ESG_AI_PROVIDER = 'anthropic'` and
`$env:ANTHROPIC_API_KEY = '...'`.

Or put the same lines in your local `.env` (`ESG_AI_ENABLED=true`, `ESG_AI_PROVIDER=gemini`,
`GEMINI_API_KEY=<your key>`): `.\scripts\dev.ps1 app` and `eval` start through
[`scripts/run_local.py`](../scripts/run_local.py), which copies **only** these AI settings
(`ESG_AI_*`, `OLLAMA_HOST`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`) from `.env` into the
environment of the app; a value set in the shell wins. The app itself still reads only the
environment and Streamlit secrets. (Before this launcher, settings in `.env` never reached the
app, so the page always showed the "not switched on" note.) Secrets can also go in
`.streamlit/secrets.toml`, which git ignores (a test fails if it, `.env` or anything key-like is
ever tracked).

**What the page shows.** The guided questions are the default and always work. Below them:

- analyst **off** (`ESG_AI_ENABLED` not `true`; the default, also on the public site unless Gemini
  is switched on there): a short note that free-text questions are not switched on for this site
  and that a demonstration is in the project video - no setup details;
- **on, and the provider has what it needs** (its key; the local model needs none): the
  "Ask in your own words" box, with the Google notice when the provider is Gemini;
- **on, but the key is missing** or Gemini's quota / key failed earlier in the session: a plain
  "not available right now" / "paused" message pointing to the guided questions (table above).

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
| Request timeout | Claude and Gemini: 30 seconds; local model: 180 seconds | the page says the analyst could not answer; the rest of the app is unaffected |
| Retries | one per request, after 3 seconds, and only for a server error (5xx) or a timeout - never for a used-up quota (429), a rejected key or a refusal; made by `agent.respond` for every provider, with the SDKs' own retries off so one stays one | the second failure gives the plain message above |
| Local context window | 8,192 tokens (`num_ctx`) | Ollama's own default is smaller and cuts a long prompt silently; the prompt with the six tools is about 3,000 tokens |

So one question costs at most 5 requests and 7,500 output tokens, and one session at most 50
requests. The limits are the same for every provider (`agent.LIMITS`; tests check them with the
fake Anthropic, Ollama and Gemini clients).

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
- `tests/test_ai_providers.py`, Gemini part (CI, fake Gemini client, no network): the same system
  prompt and the six tools as function declarations with the same JSON schema, automatic function
  calling off, the output cap and temperature 0 sent, the request valid for the real SDK types;
  tool results returned as function responses; bad arguments and unknown tools sent back as
  errors; mode `NONE` at the tool-call limit; extra calls not run; a runaway model cut off; safety
  stops (answer or question blocked) shown as refusals after one request; quota (429), key
  (400 / 403) and API errors (5xx, timeout) raised as `ProviderUnavailable`; a 5xx or timeout
  retried once after a wait, a 429, key error or refusal never; the client built with the key,
  Vertex AI off, a 30 s timeout and no SDK retry;
  without a key no client is built; the key comes only from the environment or Streamlit secrets
  (`GOOGLE_API_KEY` is ignored).
- `tests/test_app.py`: every page and every guided question runs and opens only the public files;
  visitors get the guided questions and a note with no setup details; no input box after 10
  questions; **with `ESG_AI_ENABLED=true` and the provider's key (read from a `.env` through
  `scripts/run_local.py`) the input box appears**, with the Google notice for Gemini; the local
  model needs no key; switched on without a key, a used-up quota and an API error each give a
  plain message and leave the guided questions working (the quota pauses free text for the
  session, an API error does not); a Gemini refusal is shown as a refusal; a Gemini answer shows
  its tool calls.
- `tests/test_repo_safety.py`: no tracked file holds anything key-like (Anthropic, Google `AIza...`,
  `GEMINI_API_KEY=` values, ...); `.env`, `.streamlit/secrets.toml` and Google credential files
  are ignored and untracked; `.env.example` holds no key; the app reads the Gemini key only
  through `agent.setting`; the `.env` launcher copies only the AI settings and the shell wins.
- [evals/ai_analyst_questions.yaml](../evals/ai_analyst_questions.yaml): 20 questions - 11 plain,
  2 on provisional data, 3 on withheld figures, 1 on a KPI that is not ranked, 3 that must be
  refused - each with the tools it needs, the calls that answer it and the expected numbers, taken
  from the public tables. Offline, every expected call is run and must return the expected
  numbers; a test does this, so the set cannot drift from the data.
- `.\scripts\dev.ps1 eval` asks the model every question and scores tool selection, numeric
  accuracy (with a tolerance per number), refusals and mentions (withheld, provisional, no causal
  wording); each run is saved under `evals/results/` and [ai_analyst_eval.md](ai_analyst_eval.md)
  shows them all. `ESG_AI_PROVIDER=gemini` works the same way; a Gemini run pauses 10 s between
  questions for the free-tier per-minute quota, retries a question once after a minute if the
  quota is hit, and stops without saving if it is still used up (a run with quota failures would
  not be comparable). Questions the provider never answered (a 5xx or timeout after the retries)
  are reported as "not scored"; `scripts/eval_ai_analyst.py --provider gemini --only q02 q03`
  re-runs just those, and a re-run replaces a not-scored row only - a question that already has
  a scored answer keeps it, and the re-run is saved as a variability note.

### Evaluation results (2026-10-19 local models, 2026-10-22 Gemini)

The full report, per question: [ai_analyst_eval.md](ai_analyst_eval.md). The questions and the
expected numbers and texts were fixed before any model ran and were never changed.

| Model | Passed (of 20) | Passed (of answered) | Not scored | Right tool | Numbers right | Refusals right | Wrongly refused | Caveat check | Median time per question | Variability |
|---|---|---|---|---|---|---|---|---|---|---|
| Gemini `gemini-3.5-flash-lite` (free tier) | **16 / 20** | 16 / 20 | 0 | 19 / 20 | 10 / 13 | 3 / 3 | 3 | 17 / 17 | 41 s | q12: re-run passed; first scored answer (FAIL) stays official |
| `qwen2.5:3b` (local) | 13 / 20 | 13 / 20 | 0 | 19 / 20 | 8 / 13 | 3 / 3 | 1 | 17 / 17 | 18 s | - |
| `llama3.2:3b` (local) | 8 / 20 | 8 / 20 | 0 | 15 / 20 | 5 / 13 | 0 / 3 | 6 | 17 / 17 | 58 s | - |

How to read it:

- **Not scored** means the provider never answered a question (a server error or timeout after the
  retries) - an outage, not a model failure. The first Gemini run lost `q02`, `q03`, `q10` and
  `q18` to HTTP 504 from Google. They were re-run with `--only`, and the re-run answers are their
  scored answers, so the final Gemini row has none.
- **Re-runs count only for questions that were not scored.** A question that already has a scored
  answer keeps its first one as the official result, even a failed one; `--only` enforces this
  and saves the re-run as a *variability* note instead. `q12` was scored FAIL in the first run
  and passed when it was re-run: the official result stays FAIL, and the pass is recorded as
  run-to-run variability. The same model, prompt and question gave a different outcome - one
  more reason not to read a single 20-question run as exact.
- **Scoring change after seeing the results.** Required words were first matched as an exact
  phrase, so Gemini's "not *considered* material" (`q17`) failed for lack of "not material". The
  rule now accepts the words in order with up to two other words between them, for every
  provider; all saved answers were scored again without a new model call. Effect: Gemini 15 -> 16
  of 20 (`q17`), `qwen2.5:3b` 13 -> 13, `llama3.2:3b` 8 -> 8. Details in
  [ai_analyst_eval.md](ai_analyst_eval.md).
- The local models' runs did not record call arguments (runs do now), so their slips below are
  read from their answers.

**Gemini's four failures** (official results):

- `q03` (Asset-heavy GHG intensity, whole group and typical company; scored on the re-run after
  the 504s): wrong group type, then a refusal. Its four calls asked for `Asset-heavy` as a
  `peer_group` (twice, for the whole-group and the median figure) and as a `size_band` (twice).
  The tool refused all four with the allowed values of the type asked for (nine peer groups;
  Large / Mid / Small), and the model never tried `sector_group`, where Asset-heavy lives. It then
  answered that "Asset-heavy" is not a recognised peer group or size band. No figure was given,
  so nothing is wrong, but the question is not answered.
- `q11` (restatements of FY2022-23): wrong tool and wrong row. It called `restatement_summary`
  (level `overall`) instead of `group_metric(material_restatement_share, year FY2022-23)` and
  gave the all-years share, 6.66%, as the FY2022-23 share (expected 14.1%).
- `q12` (IT services renewable share, FY2025-26; first scored answer): three `group_metric`
  calls, then a refusal; the 68.1% and the "provisional" mention are missing. That run did not
  record call arguments, so what it sent in those three calls is not available; the refusal's
  list of peer groups (Financials, Energy & utilities) suggests a group-type slip, but that is an
  inference. In the re-run (variability, not counted) it first sent `group_type="sector_group",
  group_value="IT services"` (refused: allowed Asset-heavy, Asset-light, Financials), then
  corrected to `peer_group` and answered 68.1%, provisional.
- `q15` (Metals & mining renewable share, withheld): wrong group type, then a refusal. Its answer
  lists "Asset-heavy, Asset-light, and Financials" - the allowed values the tool returns when
  `Metals & mining` is asked for as a `sector_group` (it is a `peer_group`) - so the "withheld"
  mention is missing. (From the first run, before arguments were recorded.)

**The failure common to the models: confusing the group types.** The data has six kinds of group
(`sector_group`: Asset-heavy / Asset-light / Financials; `peer_group`: nine industry groups such
as IT services or Metals & mining; `ranking_group`; `size_band`; `ownership_type`; `all`), and
some names exist in more than one. Gemini sent `IT services` and `Metals & mining` as sector
groups and `Asset-heavy` as a peer group and a size band (`q03`, `q12`, `q15`); `qwen2.5:3b` sent
the group names `Asset-heavy` and `Automobiles` as the group type itself (`q03`, `q14`) and read
the all-companies row for IT services (`q12`). The tool refuses every such call, as designed, so
no wrong figure comes from it; the cost is a refusal or a give-up instead of an answer. Gemini
corrected itself in one run of `q12` and not in the others.

*Implemented in v2 (the v1 results above are unchanged):* `group_type` is optional in
`group_metric`. When it is left out or wrong, it is found from `group_value` if only one group type
has that value (`Metals & mining` -> `peer_group`; the result says so in a note). If several do
(`Asset-heavy` is both a `sector_group` and a `ranking_group`), the error lists the matching types.
`top_movers_confirmed` and `restatement_summary` errors name the kind a value really is ("'Metals &
mining' is a peer_group, not a ranking_group"). The tool descriptions now say that a restatement
share for one year is `group_metric(material_restatement_share, year=...)` and that
`restatement_summary` is for breakdowns. The v2 run is evaluated fresh on the same 20 questions
(its own section in [ai_analyst_eval.md](ai_analyst_eval.md)) and on 5 held-out questions
([evals/ai_analyst_holdout.yaml](../evals/ai_analyst_holdout.yaml)) that were written before the run
and are not used to tune anything.

**What this means, plainly.** Gemini's free tier is the most accurate of the three (16 of 20, 10
of 13 numbers) but not steady: one question passed on one run and failed on another. The small
local `qwen2.5:3b` gets about a third of the numbers wrong or missing, and `llama3.2:3b` is not
usable here. Besides the group types, `qwen2.5:3b` gave a number that is not in the tool result
("10 companies" for 80% of emissions, where the tool said 4), read the all-years restatement
share as FY2022-23 (as Gemini did), refused one answerable question and gave one company rank
without its group size.

The guardrails did their part: no invalid call reached the data, nothing outside the public
tables was used, and every number shown under an answer is the true tool result - which is how a
reader can catch the slips above. For numbers, the guided questions (same tools, no model) are
exact. The Claude provider is wired and tested but was not evaluated (no key on this machine).

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
- The Claude provider has not been evaluated live (no key on this machine). Gemini's free tier
  answered 16 of 20 evaluation questions right, and one of the 20 changed outcome between two
  runs; its server errors (HTTP 504) are retried once, and an answer it cannot give falls back
  to the guided questions.
- All models confuse the group types now and then (evaluation above); the tool refuses such a
  call, so the cost is a refusal, not a wrong figure.
- The limits apply per browser session; someone who reloads the page gets a new session. That is
  why the public site may only use Gemini's free tier with billing off: the worst a visitor can
  do is use up the day's free quota, after which the page falls back to the guided questions.
