# Start here

## The project in three lines

1. Listed Indian companies publish sustainability reports (BRSR) as machine-readable files; they
   are public but unusable in a spreadsheet.
2. ESG Lens India turns the NIFTY 50 filings of four years into a tested warehouse of comparable
   numbers: intensities, percentages, peer rankings, and a tracker of figures that companies
   quietly changed a year later.
3. It runs on a laptop, every rule is written down, and it is not an ESG rating or investment
   advice.

## Reading order

| # | Read | To learn |
|---|---|---|
| 1 | this page | the shape of the project |
| 2 | [data_model.md](data_model.md) | the tables and how they join |
| 3 | [kpi_definitions.md](kpi_definitions.md) | what each KPI means and how it is computed |
| 4 | [business_rules.md](business_rules.md) | units, scale corrections, overrides, materiality vs requirement |
| 5 | [company_identity.md](company_identity.md) | companies, peer groups, sectors, structural breaks |
| 6 | [restatement_method.md](restatement_method.md) | how restatements are found and classified |
| 7 | [publication_policy.md](publication_policy.md) | what may be published and what may not |
| 8 | [how_to_add_filings.md](how_to_add_filings.md), [data_status.md](data_status.md) | adding a filing; what is loaded |

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
`intermediate`, `marts`).

## The five tables to know

| Table | One row is | Example question it answers |
|---|---|---|
| `fct_company_year` | a company in a financial year, with every KPI | "What was Infosys's renewable share of energy in FY2025-26?" |
| `fct_esg_value` | one value of one metric from one filing, with its citation | "Which filing does this Scope 1 number come from, and was it replaced?" |
| `fct_restatement` | a number first filed for year Y against the same number in the next report | "Which companies changed last year's water figures, and by how much?" |
| `fct_peer_benchmark` | a peer group in a year for one KPI | "What is the median GHG intensity of IT services companies?" |
| `dim_company_year` | a company in a financial year: period, boundary, size, breaks | "Is this year comparable with the last one, or was there a merger?" |

For anything published use `rpt_public_company_year` and `rpt_public_restatement_summary`
(derived values only).

## Where rules and decisions live

| What | Where |
|---|---|
| Why a tool or approach was chosen | `docs/adr/` (one short record per decision) |
| How values are normalised and corrected | [business_rules.md](business_rules.md) |
| Editable rules: peer groups, materiality, KPI list, overrides, accepted exceptions | `dbt/seeds/*.csv` (each has an entry in `dbt/seeds/_seeds.yml`) |
| What every column means, and the data types that are enforced | `dbt/models/*/_*.yml` |
| Checks that must hold | `dbt/tests/` (data) and `tests/` (Python) |

## How to run (Windows, PowerShell)

```powershell
.\scripts\dev.ps1 setup       # once: virtual environment, packages, dbt deps
.\scripts\dev.ps1 dbt-build   # build and test the whole warehouse (about 3 minutes)
.\scripts\dev.ps1 test        # Python tests
```

New filings: follow [how_to_add_filings.md](how_to_add_filings.md), then `intake`, `parse`,
`load`, `dbt-build`. A faster build of the core only: `dbt build --selector daily` from `dbt/`.
