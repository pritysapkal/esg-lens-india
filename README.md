# ESG Lens India

**Open, reproducible ESG analytics on SEBI BRSR filings of the NIFTY 50 companies.**

ESG Lens India turns the machine-readable BRSR (Business Responsibility and Sustainability Report)
XBRL filings published on NSE into a tested analytics warehouse, a semantic layer of ESG metrics,
company report cards, and a small AI analyst - all open source and runnable on a laptop.

> **Disclosure Quality Score is NOT an ESG rating.** It measures how complete, consistent and
> internally coherent a company's BRSR disclosures are - not how sustainable the company is.
> Nothing in this project is investment advice.

## Scope

- **Companies:** the official NIFTY 50 constituents (niftyindices.com list), plus companies with
  listing CSVs that are no longer in the index (currently WIPRO, flagged `in_universe = false`).
- **Years:** FY2022-23 to FY2025-26. That is **197 listed filings, 196 received**; M&M FY2023-24
  is listed by NSE, but NSE does not serve the file.
- **Taxonomies:** 5 SEBI BRSR versions are in use: 2021-09-30, 2023-06-30, 2024-04-30, 2025-05-31
  and 2026-02-28.

Live status: [docs/data_status.md](docs/data_status.md).

## Problem

SEBI requires the top 1,000 listed companies to file BRSR, and the XBRL versions are public. But:

- each filing has ~2,000 facts over ~618 concepts, 658 contexts, 35 dimension axes and 11 units -
  not usable in a spreadsheet;
- the SEBI taxonomy changes between years (5 versions across FY2022-23 to FY2025-26), so the
  same metric can live under different concepts, and even the entity identifier changes (CIN
  before 2026-02-28, ISIN after);
- each file carries current **and** prior-year values, so silent restatements go unnoticed;
- there is no free, transparent, cross-company view of these disclosures.

## Architecture

```
 manual download ──► data/raw/listing/*.csv ──► discover.py ──► listing.parquet
 (NSE website)  └──► data/raw/xbrl_inbox/*.xml ──► intake.py ──► data/raw/xbrl/<ISIN>/<year>/
                                                   (sha256, match,      (+ manifest.csv)
                                                    never overwrite)           │
                       todo.py ──► docs/data_status.md                         ▼
                                                        parse_xbrl.py (lxml)
                                                               │
                                       data/processed/{contexts,units,facts,text_facts}.parquet
                                                               │
 ┌──────────────────────────── dbt Core on DuckDB (data/warehouse/esg_lens.duckdb) ───────────┐
 │  seeds (concept_metric_map, nic_sector_map)                                                │
 │  bronze/staging (views) ─► silver/intermediate (views) ─► gold/marts (tables, Kimball star) │
 │  snapshots (SCD2 restatements) · dbt tests + dbt-expectations + Elementary                  │
 │  MetricFlow semantic layer                                                                  │
 └───────────────┬───────────────────┬───────────────────┬───────────────────┬────────────────┘
                 ▼                   ▼                   ▼                   ▼
              Power BI             Excel        Streamlit report cards   MCP AI analyst

 Orchestration (week 13): Airflow 3 + Astronomer Cosmos (Docker), watching the inbox · CI: GitHub Actions
 Prod target (later): Databricks Free Edition
```

## Status

| Module | Path | Status |
|---|---|---|
| Scaffold, CI, pre-commit | repo root | ✅ Week 1 |
| Module 1 - Manual intake pipeline (listing, universe, taxonomy scan, intake, status) | `ingestion/{discover,universe,taxonomy,intake,todo}.py` | ✅ Done |
| XBRL parser -> Parquet | `ingestion/parse_xbrl.py` | 🔲 Stub |
| dbt staging / intermediate / marts | `dbt/models/` | 🔲 Sources placeholder only |
| Concept -> metric mapping | `dbt/seeds/concept_metric_map.csv` | 🟡 6 seed rows |
| Snapshots (restatement tracker) | `dbt/snapshots/` | 🔲 Not started |
| Data quality (tests, Elementary) | `dbt/` | 🔲 Packages installed |
| Semantic layer (MetricFlow) | `dbt/models/` | 🔲 Not started |
| Power BI / Excel | `dashboards/` | 🔲 Not started |
| Streamlit report cards | `app/` | 🟡 Placeholder page |
| AI analyst (MCP) | `ai/` | 🔲 Not started |
| Orchestration (Airflow + Cosmos) - watches the inbox, never downloads | `orchestration/` | 🔲 Week 13 |

## Setup (Windows 11, PowerShell)

Prerequisites: Python **3.12** (`py -3.12 --version`), Git. Nothing is installed globally.

```powershell
git clone <repo-url> esg-lens-india
cd esg-lens-india

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt     # includes requirements.txt
pre-commit install
Copy-Item .env.example .env

pytest -q
cd dbt
dbt deps  --profiles-dir .
dbt debug --profiles-dir .
dbt seed  --profiles-dir .
cd ..
```

Or in one go: `.\scripts\dev.ps1 setup`. Other tasks: `.\scripts\dev.ps1 lint|test|intake|todo|parse|build|app`
(Linux/CI: `make <target>`). To add filings, see [docs/how_to_add_filings.md](docs/how_to_add_filings.md).

> dbt always runs from `dbt/` with `--profiles-dir .` - the profile lives in the repo, not in `~/.dbt`.

### Updating dependencies

`requirements*.txt` are full locks (direct deps listed first). To upgrade: bump the direct pins,
install into a fresh venv, run `pip check`, then re-freeze. `click` is capped `<8.5` by sqlfluff.

## Repository layout

```
ingestion/     Python: listing -> manual intake -> status report -> parse XBRL -> Parquet
dbt/           dbt project `esg_lens` (DuckDB), seeds, snapshots, tests
data/          raw / processed / warehouse (git-ignored contents)
tests/fixtures/ synthetic test data (no real filings are committed)
app/           Streamlit report-card app
dashboards/    Power BI / Excel
ai/            MCP-based AI analyst
orchestration/ Airflow 3 + Cosmos (later)
docs/          ADRs, metric definitions, open questions
```

## Data source & compliance

BRSR filings are public disclosures that NSE publishes under SEBI rules. The
[NSE Terms of Use](https://www.nseindia.com/static/nse-terms-of-use) (updated 29/10/2025)
prohibit automated data collection (clause 9) and redistribution without written permission
(clause 8). This project therefore works as follows
([ADR 0002](docs/adr/0002-manual-intake-nse-terms.md)):

- **Manual download only.** Listing CSVs and XBRL files are downloaded by hand into
  `data/raw/listing/` and `data/raw/xbrl_inbox/`. No code makes requests to `nseindia.com` or
  `nsearchives.nseindia.com`.
- **No redistribution.** Raw NSE files live under the git-ignored `data/` folder and are never
  committed. Tests use synthetic fixtures. Real-data tests skip when the files are absent.
- **Derived metrics only, cited as plain text.** Published outputs show computed metrics, never
  raw files. Each metric cites its source filing as plain text (company, report, financial year,
  NSE filing date), e.g. "HDFC Bank Limited, BRSR FY2025-26, filed on NSE 11-Sep-2026". There are
  no hyperlinks to `nseindia.com` or `nsearchives.nseindia.com` URLs.
- **Universe.** The NIFTY 50 constituents list comes from niftyindices.com and is saved locally.

Workflow: [docs/how_to_add_filings.md](docs/how_to_add_filings.md). Status:
[docs/data_status.md](docs/data_status.md).
