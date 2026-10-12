# Publication policy

What may leave this laptop and what may not. Written in plain English so it can be followed
without legal training. **We assume we have no permission from NSE to republish its content**
(see [ADR 0002](adr/0002-manual-intake-nse-terms.md)); this policy is built on that assumption.

## The rule in one line

**Only values we calculate are public; filed values - including filed percentages - stay local
and are shown publicly only as gaps, percentiles or peer statistics.**

## Public

Values that are the result of our own work on the filings:

- intensities per Rs crore of turnover that we compute (GHG, energy, water, waste);
- percentages and ratios that we compute (renewable share, waste recovery rate, women in
  workforce, waste balance gap, fatalities per 10,000 workforce);
- gaps we compute (pay-equity gap, attrition gap);
- percentiles and rankings within a peer group; peer-group medians and quartiles (also for KPIs
  whose underlying value is filed: the position is ours, the value is not shown);
- group figures of the semantic layer (whole-group ratios, medians, shares and counts), for
  groups of 5 companies or more;
- the label of the denominator a company used for its filed intensity (`*_filed_basis`);
- Disclosure Quality Scores: the total, the component scores, grade, rank, percentile, the
  provisional flag, assurance level and scope, and reason codes (not the counts behind them, and
  not which voluntary indicators a company answered);
- restatement classifications and counts (how many, what share, which class);
- yes / no flags (any fatality, Scope 3 disclosed, comparability break, KPI flags);
- names, peer groups, sector groups, financial years;
- a **plain-text source citation**: company, report, financial year, filing date - for example
  "HDFC Bank Limited, BRSR FY2025-26, filed on NSE (date)".

## Not public

- **Raw filed values copied from filings**: absolute emissions (tCO2e), energy (GJ), water (kl),
  waste (t), turnover (INR), headcounts, and raw counts (injuries, fatalities, complaints);
- **filed percentages and rates**, which are copied values too: share of wages paid to women,
  women on the board, attrition rates, LTIFR, days payable, related-party shares, MSME sourcing,
  well-being spend, POSH complaints, and the intensities as the company filed them;
- group totals of filed values (total emissions, energy, water, waste, turnover or headcount
  of a sector or peer group), whatever the size of the group;
- anything that gives a filed value back by simple arithmetic: the filed-versus-computed ratios
  (ratio x our intensity = the filed intensity), a company's own KPI value in the percentile
  table, and the minimum and maximum of a peer group (each is one company's value);
- original and restated values of a restatement, and any text copied from a filing (the
  `stated_reason` snippet);
- the raw XBRL files, the listing CSV files and everything under `data/`;
- **links to NSE** (no URL to the exchange in any published table, page or citation).

## How the warehouse enforces it

| Mechanism | What it does |
|---|---|
| `public_safe` on every column | Each column of `fct_company_year`, `fct_esg_value`, `fct_peer_benchmark`, `fct_company_kpi_percentile`, `fct_restatement` and `fct_disclosure_quality` carries `config.meta.public_safe: true / false` in `dbt/models/marts/_marts.yml`. For KPIs the flag comes from the seed `kpi_catalogue.csv`. |
| `rpt_public_company_year` | The company-year KPIs with **only** public-safe columns. Use this, not `fct_company_year`, for anything published. |
| `rpt_public_disclosure_quality` | The Disclosure Quality Score with its component scores, grade, rank, percentile and reason codes. The counts behind the components (`int_dqs_components`, `int_dqs_leadership_disclosure`: which metrics are missing, which voluntary indicators were answered, how many checks failed) stay local. |
| `rpt_public_restatement_summary` | Restatement classes, counts and percentages. No original or restated value. |
| `fct_peer_benchmark`, `fct_company_kpi_percentile` | Public: medians, quartiles, counts, percentiles. Not public: `min_value` / `max_value` and the percentile table's `value` column (marked `public_safe: false`). |
| Semantic layer (`dbt/models/semantic`) | Every metric carries `meta.public_safe` from `kpi_catalogue.csv`. Sums of filed values exist only as hidden building blocks of a ratio and are never public. A group figure built on filed values (`..._agg`, `..._median`) may be published only where its companies metric is 5 or more: the layer returns every row, so **the publishing tool must drop the smaller groups** ([semantic_layer.md](semantic_layer.md), saved query `public_rule_min_5_companies`). The views `sem_*` hold raw values and stay local. |
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

## Two things to know

- **Filed percentages are not public** (decision of 2026-10-10, ADR 0004). A percentage a company
  filed is as much a copied value as a tonne figure. It is still used: `pay_equity_gap_pp` and
  `attrition_gap_pp` are our own calculations on top of it, and percentiles and peer medians place
  a company without showing the number. 25 of the 73 KPIs are public (14 of the 62 in
  `fct_company_year` and the 11 of the Disclosure Quality Score), 48 are not.
- **Known exceptions.** The 143 rows of `dbt/seeds/known_kpi_exceptions.csv` are not 143 separate
  problems but **three reviewed categories**: the filed GHG intensity uses another denominator
  than per rupee (107 company-years, see `ghg_intensity_filed_basis`); the filed waste figures
  do not add up, i.e. a waste balance gap above 20% (28); and waste recovered exceeds waste
  generated (8, kept and flagged, not ranked). None of them is published as a value.

## If in doubt

Do not publish it. Ask whether the number could be produced by someone who only had our
calculated tables; if the answer is no, it is a copied value.
