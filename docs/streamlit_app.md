# Streamlit report card

Week 13. The public face of ESG Lens India: a small web app that anyone can open. Code in
[`app/`](../app/); start it with `.\scripts\dev.ps1 app` (or `streamlit run app/streamlit_app.py`).

## The one rule: it reads only the public tables

The app reads **only** the Parquet copies of the public models in `exports/public`
(`rpt_public_*`: values ESG Lens India calculates, never filed values -
[publication_policy.md](publication_policy.md)). There is one door to the data,
[`app/data.py`](../app/data.py): it accepts only a name from its list of seven public tables and
opens the file itself.

`tests/test_app.py` checks this two ways:

- **statically**: no file under `app/` mentions DuckDB, the warehouse, `exports/local`, `data/`,
  a gold or staging table, or reads a file on its own (only `app/data.py` may);
- **while running**: an audit hook records every file Python opens while every page of the app
  runs (`streamlit.testing`). The test fails if any data file outside `exports/public` is opened,
  or a Parquet file that is not a public table.

## Pages

| Page | What it shows | From |
|---|---|---|
| Overview | Six headline figures for the latest year and five insights, each computed from the tables (concentration, whole group vs typical company, confirmed year-on-year moves, restatements, disclosure quality) | group metrics, concentration, year-on-year, restatement summary |
| Company report card | Pick a company and year: Disclosure Quality Score, grade, rank and percentile in the ranking group, the six component scores, the reasons points were lost, assurance; computed intensities against the group's typical company; percentile bars grouped **Environment / Social / Governance** and sorted within each group, coloured by better half (blue) or worse half (orange) of the ranking group, with the number on every bar and a marker so that 0 is visible; KPIs that are not ranked listed apart, with the reason ("not ranked for this group (not material)", "n<5") | disclosure quality, company year, company percentile, group metrics |
| Sectors | Any published group figure by sector group, peer group, ranking group, size band or ownership, year by year; withheld cells read **n<5 (withheld)**, restatements of the latest year **not yet observable**; chart of the shown values (intensities on a log axis labelled 1 / 10 / 100 / 1,000) and the company counts behind them | group metrics |
| Concentration | Pareto chart of company shares of the year's Scope 1+2 emissions (shares only, no tonnes), top 1 / 5 / 10 and companies needed for 80% | concentration |
| Ask the data | **Guided questions** (default, no language model): six question types built from dropdowns, each one call of a validated tool, answered with a sentence, a table and the query used. Below it, the AI analyst for questions in your own words - where it is switched on: locally with any provider, on the public site only with Gemini's free tier; otherwise visitors see a short note instead ([ai_analyst.md](ai_analyst.md)) | all seven, through the same fixed tools |
| About & Methodology | Sources, compliance approach, publication policy, DQS in two lines, tech stack, the publication rule, how to read the figures, limits, where the details are | - |

Labels that appear wherever they apply:

- **Provisional**: FY2025-26 has no later report yet; a yellow note on every page that shows it.
- **n<5 (withheld)**: a group statistic with fewer than 5 companies behind it. Never a zero.
- **not yet observable**: a restatement figure of the latest year.
- **Ranking status**: why a KPI has no rank (not material for the group, fewer than 5 companies,
  value flagged, no direction).
- Every page ends with the source note and "not an ESG rating, not investment advice".

Charts use one colour per sector group (blue Asset-heavy, orange Asset-light, green Financials),
validated for colour-blind separation; each chart has a table next to or under it, so colour is
never the only way to read it. Tables are cached with `st.cache_data`.

## Look and feel (Week 14 polish)

Presentation only; no figure or rule changed. Theme in `.streamlit/config.toml` (muted teal).
`app/layout.py` holds the shared page header, footer, sidebar pieces (financial-year filter,
"About this project"), KPI cards and the "Not shown" message; `app/format.py` the number
formats. Page filters live in the sidebar. `tests/test_app_smoke.py` checks every page loads with
the AI analyst off and that headline numbers match the public tables.

## Deployment (Streamlit Community Cloud)

**Decision (2026-10-18): the public Parquet files are committed.** `exports/public/rpt_public_*.parquet`
(seven files, about 120 kB) are in git, so the app runs on Community Cloud straight from the
repository, with no warehouse and no build. They hold derived values only - the same tables the
publication policy already allows to be published - and the policy now says so
([publication_policy.md](publication_policy.md), "Git"). The Excel workbooks and everything in
`exports/local` stay out of git. Pushing the repository publishes these files.

Keeping them current: after new filings, `dbt-build` then `bi-export` rewrites them (sorted, so a
file changes only when its data does); commit them with the code. A test checks that nothing but
these seven files is tracked under `exports/`, and `scripts/check_public.py` (also in CI and the
last task of the Airflow DAG) checks their columns.

Steps on [share.streamlit.io](https://share.streamlit.io): New app -> this repository -> main
file `app/streamlit_app.py`. Community Cloud installs `app/requirements.txt` (only Streamlit,
pandas, PyArrow, Plotly and the Anthropic SDK, same pins as `requirements.txt`; the Ollama
client is not needed there; the Google Gen AI SDK is, for the optional Gemini analyst).
`.streamlit/config.toml` switches off Streamlit's usage statistics
and hides the developer toolbar from visitors.

**The guided questions are the default and always on. The AI analyst is off unless you switch
on Gemini's free tier** - the only provider allowed on the public site:

- **Off (default):** add nothing to the app's *Secrets*. Visitors get the guided questions (the
  same tools, no model) and a short, plain note that free-text questions are not switched on for
  this site and that **a demonstration of the AI analyst is in the project video** - no setup
  details.
- **Gemini, free tier (optional):** in *Manage app -> Settings -> Secrets* add

  ```toml
  ESG_AI_ENABLED = "true"
  ESG_AI_PROVIDER = "gemini"
  GEMINI_API_KEY = "<your Google AI Studio key>"
  ```

  Rules: the key lives **only** in these Secrets (and your local env / `.env`), never in the
  repository; **NEVER enable billing on the Google Cloud project of this key** - with billing off
  the worst case is a used-up free quota, never a bill. Every session keeps the limits (10
  questions, 4 tool calls and 5 requests per question, 1,500 output tokens, 30 s timeout), and
  visitors see the notice *"Questions are sent to Google's Gemini API; on the free tier Google may
  use them to improve its products."* above the box.
- **When Gemini cannot answer** - the free quota is used up, the key is missing or rejected, or the
  API fails - the page says so in one plain sentence and points to the guided questions, which keep
  working; a used-up quota pauses free text for the rest of the session. Nothing crashes, and no
  error code or setting name is shown (details: [ai_analyst.md](ai_analyst.md), "Gemini").
- **Never** put `ANTHROPIC_API_KEY` (paid per token) or the `ollama` provider (no local model on
  Community Cloud) in the deployment's Secrets: the per-session limits reset with every page
  reload, so a paid key behind a public page could be spent by anyone.

To record the demonstration, run the app locally (`$env:ESG_AI_ENABLED = 'true'`, or the same
lines in `.env`; see [ai_analyst.md](ai_analyst.md)).

**Look and readability.** Page title "ESG Lens India - public report card". Every chart uses 14 px
text (`ui.readable`: Streamlit's chart theme otherwise draws axis labels at 12 px); checked with
full-page screenshots of every page at 1440 px width and 100% zoom, where the smallest text is
14 px. No table shows a raw column name (a test walks every page and every guided question).
Colours: one per sector group, and blue / orange for better / worse half, all checked for
colour-blind separation; every coloured mark also carries its number or label.

## Limitations

- The app shows only what the public models hold: no filed values, and no balanced-panel or
  statistics results except as quoted text on the Overview.
- The public files are a snapshot: the app is as current as the last `bi-export` that was
  committed.
- KPI percentiles exist only for KPIs the warehouse ranks; a KPI not material for a group has a
  status, not a rank.
