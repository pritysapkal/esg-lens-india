# Start here

## The project in three lines

1. Listed Indian companies publish sustainability reports (BRSR) as machine-readable files; they
   are public but unusable in a spreadsheet.
2. ESG Lens India turns the NIFTY 50 filings of four years into a tested warehouse of comparable
   numbers: intensities, percentages, peer rankings, a tracker of figures that companies
   quietly changed a year later, and a score for how well each company discloses.
3. It runs on a laptop, every rule is written down, and it is not an ESG rating or investment
   advice.

## Reading order

| # | Read | To learn |
|---|---|---|
| 1 | this page | the shape of the project |
| 2 | [project_plan.md](project_plan.md) | what is done, what changed from the first plan, what comes next |
| 3 | [data_model.md](data_model.md) | the tables and how they join |
| 4 | [kpi_definitions.md](kpi_definitions.md) | what each KPI means and how it is computed |
| 5 | [business_rules.md](business_rules.md) | units, scale corrections, overrides, materiality vs requirement |
| 6 | [company_identity.md](company_identity.md) | companies, peer groups, sectors, structural breaks |
| 7 | [restatement_method.md](restatement_method.md) | how restatements are found and classified |
| 8 | [disclosure_quality_score.md](disclosure_quality_score.md) | the Disclosure Quality Score: what it measures, the formula, its limits |
| 9 | [semantic_layer.md](semantic_layer.md) | the metrics every tool must use, whole group versus typical company, how to query them |
| 10 | [analysis_findings.md](analysis_findings.md) | what the data says: twelve business questions, each with answer, insight and caveat |
| 11 | [stats_findings.md](stats_findings.md) | five questions put to a formal test, with what was fixed beforehand in [stats_hypotheses.md](stats_hypotheses.md) |
| 12 | [powerbi_build_guide.md](powerbi_build_guide.md), [powerbi_reconciliation.md](powerbi_reconciliation.md) | the Power BI and Excel engine: exports, the two models, the measures, how to build the pages, the numbers to check |
| 13 | [streamlit_app.md](streamlit_app.md), [ai_analyst.md](ai_analyst.md), [orchestration.md](orchestration.md) | the public report card, the AI analyst and its guardrails, the Airflow pipeline |
| 14 | [publication_policy.md](publication_policy.md) | what may be published and what may not (decision: [ADR 0004](adr/0004-publication-policy.md)) |
| 15 | [how_to_add_filings.md](how_to_add_filings.md), [data_status.md](data_status.md) | adding a filing; what is loaded |

## The pipeline in six boxes

```
 1 MANUAL DOWNLOAD      2 INTAKE              3 PARSE
 a person saves the  ->  files are matched  ->  each XBRL file becomes
 files from the          to the listing,        rows: facts, contexts,
 exchange website        hashed, never          units (Parquet)
 (no scraping)           overwritten
                                                      |
 6 GOLD                 5 INTERMEDIATE         4 STAGING
 star schema: facts  <-  business rules:    <-  typed, flagged copies
 and dimensions,         periods, units,        of the parsed rows,
 KPIs, benchmarks,       scale fixes, metric    nothing interpreted
 restatements            catalogue, identity
```

Boxes 1-3 are Python (`ingestion/`); boxes 4-6 are dbt on DuckDB (`dbt/models/staging`,
`intermediate`, `marts`). On top of gold sits the semantic layer (`dbt/models/semantic`,
MetricFlow): the group metrics, defined once.

## The six tables to know

| Table | One row is | Example question it answers |
|---|---|---|
| `fct_company_year` | a company in a financial year, with every KPI | "What was Infosys's renewable share of energy in FY2025-26?" |
| `fct_esg_value` | one value of one metric from one filing, with its citation | "Which filing does this Scope 1 number come from, and was it replaced?" |
| `fct_restatement` | a number first filed for year Y against the same number in the next report | "Which companies changed last year's water figures, and by how much?" |
| `fct_peer_benchmark` | a peer group in a year for one KPI | "What is the median GHG intensity of IT services companies?" |
| `fct_disclosure_quality` | a company in a financial year, with its Disclosure Quality Score | "How far can this company's report be trusted, and what cost it points?" |
| `dim_company_year` | a company in a financial year: period, boundary, size, breaks | "Is this year comparable with the last one, or was there a merger?" |

For anything published use `rpt_public_company_year`, `rpt_public_disclosure_quality`,
`rpt_public_group_metrics`, `rpt_public_restatement_summary`, `rpt_public_concentration`
(rank and share of emissions) and `rpt_public_company_percentile` (position in the ranking
group) - derived values only.

For a figure about a **group** (a sector, a peer group, a year) do not write your own SQL. On
the laptop, ask the semantic layer for the metric by name, for example `mf query --metrics
ghg_intensity_agg --group-by company_year__sector_group`. For anything public, read
`rpt_public_group_metrics`: the same figures, with statistics left empty for fewer than 5
companies. Both come from one definition in `kpi_catalogue.csv`
([semantic_layer.md](semantic_layer.md)).

## Where rules and decisions live

| What | Where |
|---|---|
| Why a tool or approach was chosen | `docs/adr/` (one short record per decision) |
| How values are normalised and corrected | [business_rules.md](business_rules.md) |
| Editable rules: peer groups, materiality, KPI list, overrides, accepted exceptions, score weights and assurance points | `dbt/seeds/*.csv` (each has an entry in `dbt/seeds/_seeds.yml`) |
| What every column means, and the data types that are enforced | `dbt/models/*/_*.yml` |
| Checks that must hold | `dbt/tests/` (data) and `tests/` (Python) |
| The business questions and their SQL | `analysis/sql/q01_...sql` to `q12_...sql`; findings in [analysis_findings.md](analysis_findings.md) |
| Power BI and Excel | `scripts/export_bi.py` (exports), `scripts/build_powerbi.py` (generates `powerbi/`), `scripts/build_excel.py`; checks `scripts/reconcile_bi.py`, `check_tmdl.ps1`, `check_excel.ps1` |
| Report card, AI analyst, Airflow | `app/` (`data.py` is the only door to data, `views/` the pages, `ai_analyst/` the tools and loop), `evals/`, `orchestration/` (`pipeline.py` lists the tasks, `dags/` the DAG) |
| The statistics studies | `analysis/stats/` (one module per study, `run.py`, `validate.py`); hypotheses in [stats_hypotheses.md](stats_hypotheses.md), findings in [stats_findings.md](stats_findings.md) |

## How to run (Windows, PowerShell)

```powershell
.\scripts\dev.ps1 setup       # once: virtual environment, packages, dbt deps
.\scripts\dev.ps1 dbt-build   # build and test the whole warehouse (about 3 minutes)
.\scripts\dev.ps1 test        # Python tests
.\scripts\dev.ps1 semantic    # regenerate the semantic layer from the catalogue and validate it
.\scripts\dev.ps1 analysis    # run the 12 business questions; results in data/processed/analysis
.\scripts\dev.ps1 stats       # run the 5 statistics studies; results in data/processed/stats
.\scripts\dev.ps1 bi-export   # Parquet for Power BI (exports/local, exports/public) and the Excel workbook
.\scripts\dev.ps1 app         # the public report card (Streamlit) on http://localhost:8501
.\scripts\dev.ps1 eval        # AI analyst evaluation (live part needs ANTHROPIC_API_KEY)
.\scripts\dev.ps1 airflow     # Airflow 3 with the pipeline DAG in Docker, http://localhost:8080
.\scripts\dev.ps1 airflow-test  # the whole DAG once, in Docker, with the network switched off
```

New filings: follow [how_to_add_filings.md](how_to_add_filings.md), then `intake`, `parse`,
`load`, `dbt-build`. A faster build of the core only: `dbt build --selector daily` from `dbt/`.
