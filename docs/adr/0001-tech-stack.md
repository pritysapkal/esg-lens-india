# ADR 0001 - Core tech stack

- **Status:** Accepted. The "Ingestion HTTP" row is superseded by
  [ADR 0002](0002-manual-intake-nse-terms.md): no automated downloads.
- **Date:** 2026-10-07

## Context

ESG Lens India ingests SEBI BRSR XBRL filings (~1,000 companies x several financial years,
~2,000 facts per filing) and serves analytics through Power BI, Excel, a Streamlit app and a
small AI analyst. It is a solo capstone on a Windows laptop with no cloud budget, but it should
be portable to a production target (Databricks Free Edition) later. The work split is
Data Analytics 40% / Analytics Engineering 45% / Data Engineering 15%.

## Decision

| Concern | Choice | Why |
|---|---|---|
| Raw file format | **Parquet** (via pyarrow) | Columnar, typed, compressed; read natively by DuckDB, pandas, Spark/Databricks. Immutable files are easy to version per filing. |
| XBRL parsing | **lxml** (+ Arelle for validation/taxonomy lookups) | BRSR instances are plain XBRL 2.1 + dimensions; lxml is fast, low-memory and gives full control over contexts/units/facts. Arelle is heavy but authoritative - used to cross-check, not in the hot path. |
| Warehouse (dev) | **DuckDB** | In-process, zero-admin, single file, excellent Parquet support, fast on a laptop. Data volume (millions of facts) is far below where a server DB is needed. |
| Transformation | **dbt Core** + dbt-duckdb | SQL-first, version-controlled models, tests, docs, lineage, snapshots (SCD2 for restatements). Same project can later target Databricks with a profile change. |
| Data quality | dbt tests, **dbt-expectations**, **Elementary** | Declarative tests in the same repo; Elementary adds anomaly detection and a shareable report. |
| Semantic layer | **MetricFlow** | One definition of each metric shared by BI tools, the app and the AI analyst. |
| Ingestion HTTP | httpx + tenacity | Modern client with timeouts; tenacity gives clean retry/backoff policies for polite scraping. |
| Orchestration | **Airflow 3 + Astronomer Cosmos** - deferred to week 13 | Industry standard; Cosmos maps dbt models to tasks. Needs Docker, so it is postponed to keep weeks 1-12 lightweight; until then tasks run via `scripts/dev.ps1` / `make`. |
| CI | GitHub Actions | Free for public repos; runs ruff, pytest, dbt parse on every push. |

## Consequences

- Everything runs locally with `pip` only; no services to start.
- DuckDB is single-writer: concurrent dbt runs / app writes must be avoided (the app reads only).
- Taxonomy versions change yearly, so concept mappings are keyed by `taxonomy_version` (seed `concept_metric_map`).
- Moving to Databricks means: Parquet -> Delta/Volumes, profile `dbt-databricks`, and checking
  DuckDB-specific SQL in models.

## Alternatives considered

- **PostgreSQL** - more operational overhead, slower for analytical scans, no gain at this scale.
- **pandas-only transforms** - no lineage, testing or docs; harder to review.
- **Arelle as the main parser** - correct but slow and memory-heavy for bulk parsing.
- **Prefect / Dagster** - good options; Airflow chosen for its ubiquity and the mature dbt integration via Cosmos.
