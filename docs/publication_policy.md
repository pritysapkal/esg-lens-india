# Publication policy

What may leave this laptop and what may not. Written in plain English so it can be followed
without legal training. **We assume we have no permission from NSE to republish its content**
(see [ADR 0002](adr/0002-manual-intake-nse-terms.md)); this policy is built on that assumption.

## The rule in one line

**Publish only what we calculate. Never publish what we copied.**

## Public

Values that are the result of our own work on the filings:

- intensities per Rs crore of turnover (GHG, energy, water, waste);
- percentages and ratios (renewable share, waste recovery rate, women in workforce, the filed
  percentages and rates such as wage share, attrition, LTIFR, days payable);
- gaps we compute (pay-equity gap, attrition gap, filed-versus-computed ratios);
- percentiles and rankings within a peer group; peer-group medians and quartiles;
- Disclosure Quality Scores;
- restatement classifications and counts (how many, what share, which class);
- yes / no flags (any fatality, Scope 3 disclosed, comparability break, KPI flags);
- names, peer groups, sector groups, financial years;
- a **plain-text source citation**: company, report, financial year, filing date - for example
  "HDFC Bank Limited, BRSR FY2025-26, filed on NSE (date)".

## Not public

- **Raw filed values copied from filings**: absolute emissions (tCO2e), energy (GJ), water (kl),
  waste (t), turnover (INR), headcounts, and raw counts (injuries, fatalities, complaints);
- original and restated values of a restatement, and any text copied from a filing (the
  `stated_reason` snippet);
- the raw XBRL files, the listing CSV files and everything under `data/`;
- **links to NSE** (no URL to the exchange in any published table, page or citation).

## How the warehouse enforces it

| Mechanism | What it does |
|---|---|
| `public_safe` on every column | Each column of `fct_company_year`, `fct_esg_value`, `fct_peer_benchmark`, `fct_company_kpi_percentile` and `fct_restatement` carries `config.meta.public_safe: true / false` in `dbt/models/marts/_marts.yml`. For KPIs the flag comes from the seed `kpi_catalogue.csv`. |
| `rpt_public_company_year` | The company-year KPIs with **only** public-safe columns. Use this, not `fct_company_year`, for anything published. |
| `rpt_public_restatement_summary` | Restatement classes, counts and percentages. No original or restated value. |
| `fct_peer_benchmark`, `fct_company_kpi_percentile` | Already public-safe: they hold only derived KPIs. |
| Tests | `assert_public_models_safe` (dbt) fails the build if a public model gets a non-public column or a column named like a raw quantity; `tests/test_kpi_catalogue.py` checks the flags against the catalogue. |
| Git | `data/`, Parquet and DuckDB files are never committed (`.gitignore`). |

## Dashboards and the public showcase

- **Full dashboards** (Power BI, Streamlit) that show raw values stay **local**. They are not
  published and their files are not shared.
- The **public showcase** uses screenshots or a demo video of those dashboards **plus derived
  numbers** from the public models. Before publishing a screenshot, check that it shows no raw
  filed quantity; crop or switch the visual to an intensity or percentile if it does.
- Every published number carries its plain-text citation and the note that the Disclosure Quality
  Score is not an ESG rating and nothing here is investment advice.

## One judgement call to know about

Percentages and rates that companies file themselves (wage share to women, attrition, LTIFR,
related-party shares) are treated as **public**: they are ratios, not quantities, and they are
listed under "percentages / ratios" above. If a stricter reading is wanted ("only numbers we
computed"), set `public_safe` to `false` for those rows in `dbt/seeds/kpi_catalogue.csv`, remove
them from `rpt_public_company_year.sql`, and the tests will hold the line.

## If in doubt

Do not publish it. Ask whether the number could be produced by someone who only had our
calculated tables; if the answer is no, it is a copied value.
