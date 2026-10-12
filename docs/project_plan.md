# Project plan (current)

The plan as it stands on 2026-10-12, after nine weeks of work. It replaces the original blueprint
wherever the two differ. Plain English on purpose.

## a) What changed from the original blueprint, and why

| Area | Original idea | What we do now | Why |
|---|---|---|---|
| Getting the files | An automated, polite downloader | **Manual intake**: a person saves the files; code only matches, hashes and files them | NSE Terms of Use clauses 8 and 9 forbid automated collection and redistribution ([ADR 0002](adr/0002-manual-intake-nse-terms.md)) |
| Scope | "BRSR filers" | **NIFTY 50 + WIPRO** (outside the index, flagged), **FY2022-23 to FY2025-26, 196 filings** (197 listed; one is not served by the exchange) | A set small enough to download by hand and check by eye |
| Week 2 | A week for the downloader | **Merged into manual intake** (Weeks 1-2) | There is no downloader to build |
| Taxonomy | One BRSR format | **Five taxonomy versions** mapped to one metric catalogue | The same metric changes name between years; even the company identifier changes (CIN, then ISIN) |
| Units | Trust the filed unit | **Evidence-based unit normalisation** (unit from the next filing, from text, or the format default) **plus approved manual overrides** in a seed | Old filings carry no usable unit; some values are a million times off |
| Comparing companies | NSE industry | **Nine peer groups, three sector groups, and a ranking rule**: rank within the peer group only if it has at least 5 companies, else within the sector group | Three steel makers are not a ranking |
| What counts | One list of metrics | **Materiality** (rank it or not, per peer group) kept apart from **disclosure requirement** (must it be filed, from which year) | A bank must file water use; ranking banks on it is meaningless |
| Year-on-year | Assume years are comparable | **Corporate events and boundary changes flag comparability breaks** | Mergers, demergers and a switch between standalone and consolidated break the series |
| Restatements | Flag every changed number | A **scale-error class** (values more than 100x apart, 10x for percentages) is set aside, and KPIs use the **best available value** (the later report) | Most "huge restatements" were unit slips, not restatements |
| Publishing | Publish the dashboards | **Publication policy: derived values only** ([ADR 0004](adr/0004-publication-policy.md)) | We have no permission to republish filed values, percentages included |
| Disclosure Quality Score | Many consistency signals, weights to be decided | **Lean score of four parts** (completeness 0.30, internal consistency 0.30, temporal consistency 0.20, assurance 0.20), each a rate; a part that cannot be tested is left out and the weights re-normalised. **Version 2** measures what is voluntary: completeness is half mandatory metrics and half Leadership indicators answered, and assurance gives half the points for the Core assurance SEBI requires and the rest for assuring the whole report | Version 1 could not tell companies apart (187 of 196 grade A): everything it measured is mandatory for the NIFTY 50. The fix changes what is measured, not the weights or cut-offs ([method](disclosure_quality_score.md)) |
| Semantic layer | Metric definitions in a semantic layer, Databricks as a stretch | **MetricFlow on DuckDB, generated from `kpi_catalogue.csv`**: 25 group metrics, each either a ratio of sums (`_agg`), a median (`_median`), a share or a count - never an average of company ratios; group figures on filed values carry a "5 companies or more" rule; Databricks not done | One definition for Power BI, Excel, Streamlit and the AI analyst; an average of intensities describes neither the group nor its typical company ([guide](semantic_layer.md)) |
| Housekeeping | - | **Hardening** before Week 8: public models, accepted-exception seed (build ends with 0 warnings), KPI catalogue as single source of truth, [START_HERE](START_HERE.md) | So the next seven weeks build on something that stays tidy |

## b) Done

| When | What | In one line | Main commit |
|---|---|---|---|
| Week 1 | Scaffold | Repository, CI, pre-commit, ADR for the tech stack | `07c6797` |
| Weeks 1-2 | Manual intake | Listing, universe, taxonomy scan, intake with hashes, status page; nothing is fetched by code | `d14a45e` |
| Week 3 | XBRL parser | 196 filings to Parquet (facts, contexts, units), cross-checked against Arelle | `4d86c17` |
| Week 4 | Staging | Typed, flagged dbt staging models with tests; synthetic data path for CI | `945534b` |
| Week 5 | Metric catalogue and normalisation | 34 metrics over 5 taxonomies, unit normalisation, turnover scale fixes, approved overrides | `6aa1b4e`, `9060ea2` |
| Week 6 | Company identity and sectors | ISIN key, name history, NIC sectors, peer and sector groups, materiality, company-year dimension, corporate events, verified seeds | `e484845`, `4ecb459`, `cc06bb4`, `0eb1339` |
| Week 7 | Gold star schema and restatement tracker | Facts and dimensions with enforced contracts, KPIs, peer benchmarks and percentiles, restatement classes, scale-error handling | `2cb3bad`, `265e856`, `a7a3f0c` |
| Hardening | Before Week 8 | Publication policy and public models, exception tracking, KPI single source, START_HERE, tags and selectors | `fa44d82`, `440c88c` |
| Week 8 | Disclosure Quality Score | One score 0-100 per company-year from four visible parts, with grade, rank in group and year, reason codes, a public model and a weight sensitivity check; then version 2: voluntary depth (Leadership indicators read from the taxonomy), beyond-compliance assurance, a grade only with three components, provisional flag for the latest year ([method](disclosure_quality_score.md)) | `cda7200`, "feat: DQS v2" |
| Week 9 | Semantic layer | 25 group metrics in MetricFlow, generated from the KPI catalogue; 4 semantic models, a time spine, 8 saved queries; `mf query` equals plain SQL on the gold tables within 1e-9 ([guide](semantic_layer.md)) | "feat: Week 9 semantic layer (MetricFlow)" |

State of the warehouse: 51 companies, 196 company-years, 21,706 metric values, 73 company-level
KPIs (25 public), 25 group metrics in the semantic layer, 4,115 compared restatement pairs, 196
Disclosure Quality Scores (version 2: median 85.0; 98 grade A, 90 B, 7 C, 1 without a grade);
full build and test in about 3 minutes with 0 warnings.

## c) Remaining weeks

| Week | Goal | Scope notes |
|---|---|---|
| 10 | **SQL business analysis** | Twelve questions answered in SQL on the gold tables, each with the query and a two-line reading. Group figures come from the semantic layer (its 8 saved queries are the starting point). |
| 11 | **Statistics studies** | A few careful studies (for example size versus intensity, assurance versus restatement), with the small-sample caveats stated. |
| 12 | **Power BI and Excel** | Two versions: the full local one (raw values, never shared) and a public one built only on `rpt_public_*`. |
| 13 | **Airflow, Streamlit report card, AI analyst** | Airflow watches the inbox and never downloads. The report card reads `rpt_public_*` only. The AI analyst answers from the public models with citations. |
| 14 | **Insight report, README polish, demo video** | A short written report of findings, a tidy README, and a 3-minute demo video of the local dashboards (checked against the publication policy). |

## d) Known limitations and open decisions

Known limitations (each documented where it belongs):

- **Survivorship bias** - today's NIFTY 50 applied to all four years; small or mixed peer groups:
  [company_identity.md](company_identity.md).
- **FY2022-23 is noisy** (inferred units, most scale errors); only three restatement pairs;
  restatement is not wrongdoing: [restatement_method.md](restatement_method.md).
- **Filed intensities use mixed denominators**; some filed values are implausible and are flagged
  or set to empty: [kpi_definitions.md](kpi_definitions.md).
- **Unit and scale rules are evidence-based, not certain**: [business_rules.md](business_rules.md).
- **Public numbers cannot be rebuilt without downloading the filings yourself**:
  [publication_policy.md](publication_policy.md).
- **The Disclosure Quality Score is still clustered** (half the scores lie between 80 and 90, no
  grade D), scores are comparable only within a year, the latest year is provisional, assurance
  is self-reported, and some voluntary indicators do not apply to Financials:
  [disclosure_quality_score.md](disclosure_quality_score.md).
- **The semantic layer does not enforce the "5 companies or more" rule itself** (the consuming
  tool must), has no live connection for Power BI or Excel, and runs on DuckDB only:
  [semantic_layer.md](semantic_layer.md).
- NIC division names and NIC code corrections are still unverified (`verified_by` empty in the
  seeds).

Open decisions - **none blocking**:

- whether to ask NSE for written permission (would widen what is public; ADR 0004);
- whether Databricks is attempted later (it was left out of Week 9; nothing depends on it).
