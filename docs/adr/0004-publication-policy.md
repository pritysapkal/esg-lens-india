# ADR 0004 - Publication policy: only calculated values are public

- **Status:** Accepted
- **Date:** 2026-10-10
- **Builds on:** [ADR 0002](0002-manual-intake-nse-terms.md) (manual intake, NSE Terms of Use)

## Context

The filings are public disclosures, but we obtain them from the NSE website, whose Terms of Use
(clause 8) forbid reproducing, storing for redistribution or publishing its content without
written permission. ADR 0002 already settled how the files are collected (by hand) and that raw
files are never committed. It did not say precisely which **numbers** may appear in what we
publish: the GitHub repository, a Streamlit report card, LinkedIn posts, the insight report.

Two readings were possible. A loose one: "no raw files, no absolute quantities, but percentages are
fine". A strict one: "nothing that was copied from a filing". The loose reading leaves a grey
zone - a percentage a company filed (share of wages paid to women, attrition, LTIFR) is copied
content exactly as a tonne figure is. We have not asked NSE for permission and do not assume it.

## Decision

**Only values we derive or calculate are public. Everything copied from a filing stays local.**

Public:

- intensities per Rs crore that we compute;
- percentages and ratios that we compute (renewable share, waste recovery rate, women in
  workforce, waste balance gap);
- pay-equity gap and attrition gap;
- percentiles and rankings within a peer group; peer-group medians and quartiles;
- Disclosure Quality Scores;
- restatement classifications and counts;
- yes / no flags, names, groups, financial years;
- plain-text source citations (company, report, year, filing date).

Stay local:

- raw filed values, **including filed percentages and rates** and the intensities as filed;
- anything that returns a filed value by simple arithmetic (filed-versus-computed ratios, a
  company's own value in the percentile table, group minimum and maximum);
- original and restated values, and text copied from a filing;
- raw XBRL and listing files, and any link to NSE.

How it is applied:

- **No NSE permission is requested** for now; the policy is designed to need none.
- **Public outputs read only from the `rpt_public_*` models** (`rpt_public_company_year`,
  `rpt_public_restatement_summary`) and from the public columns of `fct_peer_benchmark` and
  `fct_company_kpi_percentile`. This holds for GitHub, Streamlit, LinkedIn and the insight report.
- **Full dashboards** (Power BI, Excel) with raw values stay on the laptop and are shown through
  screenshots or a demo video, checked so that no raw filed value is legible.
- Every fact column carries `config.meta.public_safe`; for KPIs the flag lives in the seed
  `kpi_catalogue.csv`. dbt and pytest tests fail if a public model gains a non-public column.

Details for everyday use: [publication_policy.md](../publication_policy.md).

## Consequences

- The public KPI set is small: 14 of 62 KPI columns. Filed KPIs (wage share, attrition, LTIFR,
  related-party shares, MSME sourcing) appear publicly only as gaps, percentiles or peer medians.
  A reader of the public report card sees "40th percentile in its peer group", not the number.
- Some public values are close to filed ones: `pay_equity_gap_pp` plus `female_workforce_pct`
  gives the filed wage share back. Both are our calculations and are kept public on purpose; the
  rule is about not republishing filed values as such, not about making them unrecoverable.
- Two versions of every dashboard are needed (local full, public derived). Week 12 and Week 13
  plans account for it.
- Reviewers cannot reproduce public numbers from the repository alone: they must download the
  filings themselves ([how_to_add_filings.md](../how_to_add_filings.md)). The pipeline, rules and
  tests are fully open, which is what reproducibility means here.
- The line is enforced by code, not by memory, so adding a column forces a decision.

## Revisit if

- **NSE grants written permission** to reproduce filed values: then filed percentages, and
  possibly quantities, can be flipped to `public_safe: true` in the seed, one row at a time;
- the data is obtained from a source with clearer redistribution terms (for example the
  companies' own websites or a SEBI open-data release);
- legal advice says the strict reading is unnecessary - or not strict enough.
