# Statistics studies: hypotheses written down before the results

Week 11. This page was written and committed **before any of the tests below was run**. It says
what will be tested, how, on which data, and what will count as a result. The results go in
[stats_findings.md](stats_findings.md); every departure from this page is listed there under
"Against pre-registration", with the reason.

Why bother: with 51 companies and a free choice of years, filters and tests, almost any story
can be made "significant". Fixing the choices first is the only protection against that.

## What was already known when this was written

Honesty about the starting point. The descriptive analysis of Week 10
([analysis_findings.md](analysis_findings.md)) had already shown:

- Study 1: a two-by-two split of 34 companies with no visible association (Q10);
- Study 2: the confirmed year-on-year changes range from about -40% to +22% (Q3), and group
  figures on the balanced panel over three years (Q1);
- Study 3: **the share itself** - 115 of 241 material restatements with a direction flatter the
  trend, 47.7% (Q9). The test here adds the interval, the clustering check and the power; the
  point estimate is not new;
- Study 5: the median score by ownership type and year (Q8).

Nothing was known about Study 4. No test statistic, p-value or interval of any study had been
computed.

## Rules for all five studies

| Rule | Choice |
|---|---|
| Data | The gold tables (`fct_company_year`, `fct_disclosure_quality`, `fct_restatement`, `fct_company_kpi_percentile`, `fct_esg_value`, `dim_company`), read-only |
| Significance level | alpha = 0.05, two-sided, for every test |
| Multiple testing | **Benjamini-Hochberg** over all primary tests that are run (up to 8: one each for Studies 1, 3, 4 and 5; up to four for Study 2). A test that cannot be run because fewer than 5 companies are left is not counted. Sensitivity and robustness checks are not in the family; their p-values are reported raw and are not used for a decision |
| Decision rule | H0 is rejected when the BH-adjusted p-value is below 0.05. Whatever the outcome, the effect size, its 95% interval and the minimum detectable effect are reported |
| Unit of analysis | The **company** wherever one company contributes more than one observation. Resampling (bootstrap) and shuffling (permutation) are done by whole companies |
| Random numbers | Seed 20261013 for every study (numpy `default_rng`), 10,000 permutations, 10,000 bootstrap resamples; intervals are percentile intervals |
| Minimum group size | 5 companies, as everywhere in this project |
| Minimum detectable effect (MDE) | The smallest true effect the test would find 80 times out of 100 at alpha = 0.05 (not BH-adjusted), for the sample actually available. Method per study below |
| "Likely underpowered" | A result that does not reject H0 is called likely underpowered when the MDE is larger than the **effect of practical interest** fixed below for that study |
| Language | "associated with", never "causes", "leads to" or "because of" |
| Software | Python 3.12, numpy 2.5.3, scipy 1.18.1, statsmodels 0.15.0 (pinned in `requirements.txt`); code in `analysis/stats/` |

### Which data counts as confirmed (Week 10 rules)

Primary analyses use confirmed data only. For GHG figures, a **company-year is confirmed** when
all of these hold (the rules of Q3, applied to every company, not only to ranked groups):

- it is not the latest year (a later report exists);
- the next report repeats Scope 1 and Scope 2 unchanged or within 5% (`no_change`, `minor`);
- no unit was inferred from the next report, and nothing was restated materially;
- no emissions or turnover figure of that year was a suspected scale error;
- it is not a one-year reversal (intensity more than twice, or less than half of, both the year
  before and the year after).

A **company is `needs_review`** by the screen of Q5: on the four-year balanced panel, turnover
or emissions changed by more than -50% or +100% between the first and the latest year, or have
a one-year reversal. Such companies are left out of the primary analyses of Studies 1 and 2.

The latest year (FY2025-26) is **provisional** for GHG figures, restatements and the Disclosure
Quality Score (DQS), and is left out of every primary analysis.

Sensitivity analyses put these observations back in and are reported separately.

## Study 1. Disclosure quality and carbon intensity

**Question.** Inside a ranking group, do companies with a higher DQS have a different GHG
intensity?

| | |
|---|---|
| H0 | Within ranking groups, DQS and GHG intensity are not associated (pooled rho = 0) |
| H1 | They are associated, in either direction (pooled rho not 0) |
| Unit | Company (one observation each) |
| Year | The latest year with confirmed GHG data and a final DQS - by the rules above FY2024-25 |
| Filter | Ranking groups where GHG intensity is ranked (so not Financials); company-year confirmed; company not `needs_review`; intensity above 0; DQS built from at least three components. A ranking group stays in only with 5 or more such companies |
| Variables | `dqs_total` and the natural log of `ghg_intensity_tco2e_per_cr` |
| Within a group | Spearman rank correlation, reported per group with n (descriptive, not tested one by one) |
| Pooled statistic | Weighted mean of the group correlations, weight = companies in the group minus 1 |
| Primary test | **Stratified permutation**: DQS is shuffled within each ranking group, 10,000 times; p = (1 + number of shuffles with an absolute pooled rho at least as large as observed) / 10,001 |
| Effect size | Pooled rho with a 95% bootstrap interval: companies are resampled within their ranking group. A resample in which a group has no variation is drawn again; the number of redraws is reported |
| Sign | Negative rho = higher DQS goes with lower intensity |
| MDE | Simulation: for the group sizes found, pairs drawn with a known correlation, 1,000 data sets per value on a grid of 0.05, each tested with 999 shuffles. Reported as a Spearman rho |
| Effect of practical interest | absolute rho of 0.3 |

Note: the log changes nothing for a rank correlation (ranks are the same with or without it).
It is kept in the definition because the sensitivity checks below and the plots use it.

Sensitivity (not in the BH family): (a) all ranking groups with 3 or more companies left;
(b) the same year with unconfirmed and `needs_review` companies included; (c) FY2023-24;
(d) FY2025-26, provisional.

## Study 2. Is GHG intensity falling?

**Question.** Did the GHG intensity of the typical company change from FY2023-24 to FY2024-25?

| | |
|---|---|
| H0 | The median change in log GHG intensity is 0 |
| H1 | It is not 0 |
| Unit | Company; one value each: d = ln(intensity FY2024-25) - ln(intensity FY2023-24) |
| Filter | Balanced panel as in Q1 (filed in all four years with an intensity, no comparability break after the first year); both years confirmed; company not `needs_review` |
| Primary tests | **Wilcoxon signed-rank** on d, two-sided (exact p-value where scipy can give one, otherwise the normal approximation): (1) all companies; (2-4) each sector group with 5 or more companies. Up to four tests, all in the BH family |
| Effect size | Median change in percent, 100 x (exp(median d) - 1), with a 95% bootstrap interval (companies resampled) |
| MDE | Simulation: the observed d are centred on 0, shifted by a known amount and resampled, 2,000 data sets per shift on a grid of 0.01 in log terms. Reported as a percentage change, for a fall |
| Effect of practical interest | 5% change in one year |

A group figure here is the median of company changes (the typical company). It is not the
change of the group as a whole, which is a ratio of sums and is in Q1.

Sensitivity (not in the BH family): (a) **FY2022-23 to FY2025-26** on the balanced panel with
provisional, inferred-unit and `needs_review` values included - the long view, reported
separately and labelled as unconfirmed; (b) FY2023-24 to FY2024-25 with every confirmed pair,
without the four-year panel and without the `needs_review` exclusion.

## Study 3. Do restatements flatter the trend?

**Question.** When a company restates a figure materially, does the restatement make its trend
look better more often than a coin toss would?

| | |
|---|---|
| H0 | The share of flattering restatements is 0.5 |
| H1 | It is not 0.5 |
| Unit | Material restatement with a direction (`classification = 'material'`, `flatters_trend` not empty) |
| Filter | Values of FY2022-23 to FY2024-25 (FY2025-26 has no later report) |
| Primary test | **Exact binomial test** against 0.5, two-sided |
| Effect size | The share with a **Wilson** 95% interval |
| Clustering check | Restatements of one company are not independent. Companies are resampled with all their restatements (10,000 times): a second 95% interval, and a p-value = twice the smaller share of resamples on either side of 0.5. The design effect (cluster variance / binomial variance) and the effective number of restatements are reported |
| Decision rule, addition | If the binomial test rejects H0 but the cluster interval contains 0.5, the result is reported as **not robust to clustering** and is not claimed |
| MDE | Exact: the smallest distance from 0.5 that the binomial test finds with 80% power, at the number of restatements and at the effective number |
| Effect of practical interest | 10 percentage points away from 0.5 (a 60 / 40 split) |

Sensitivity (not in the BH family): the same test per year of the value.

## Study 4. Assurance of the whole report and later restatement

**Question.** Are company-years whose whole BRSR was assured ("All") restated less often in the
next report than those with assurance of the Core only?

| | |
|---|---|
| H0 | The odds of at least one material restatement are the same for both groups (odds ratio = 1) |
| H1 | The odds differ (odds ratio not 1) |
| Unit | Company-year |
| Filter | FY2023-24 and FY2024-25 (assurance is filed from FY2023-24; FY2025-26 has no later report); `assurance_level = 'reasonable'`; at least one compared metric in `fct_restatement` |
| Groups | `assurance_scope = 'all'` (whole report) against `'partial'` (Core only) |
| Outcome | Yes / no: at least one compared metric of that year classified `material` in the next report |
| Primary test | **Fisher's exact test**, two-sided, on the 2 x 2 table |
| Effect size | Conditional odds ratio (whole report against Core only) with an exact 95% interval. Below 1 = whole-report assurance goes with fewer restated company-years |
| Also reported | For each group, the share of compared metrics restated materially: all restated metrics of the group over all compared metrics of the group (a ratio of sums), and the median company-year share |
| Clustering check | A company appears in up to two years. **Company-cluster permutation**: each company's assurance scopes (for both years together) are passed to another company with the same years present, 10,000 times. Two statistics: the difference in the share of company-years with a restatement, and the difference in the pooled share of metrics restated |
| MDE | Exact enumeration of Fisher's test for the group sizes found, with the Core-only rate as baseline: the smallest lower and the smallest higher rate in the whole-report group found with 80% power, as a difference in percentage points |
| Effect of practical interest | 20 percentage points |

Sensitivity (not in the BH family): company-years with an "assessment" included, grouped by
scope.

## Study 5. Ownership and disclosure quality

**Question.** Do government-owned companies (PSUs) score differently from private Indian
companies on the DQS?

| | |
|---|---|
| H0 | In every year, a PSU's score is as likely to be above a private company's as below (Cliff's delta = 0) |
| H1 | Delta is not 0 |
| Unit | Company (7 government-owned, 41 private Indian in the seed); each has up to three yearly scores |
| Filter | FY2022-23 to FY2024-25; DQS built from at least three components. FY2025-26 is provisional and left out |
| Groups | `ownership_type`: Government against Private Indian. MNC subsidiaries are compared with private Indian companies only if 5 or more exist (the seed has 3, so this is not expected to run) |
| Statistic | Scores are only compared within a year (they are not comparable across years). **Stratified Cliff's delta** = (PSU-above pairs minus PSU-below pairs) / all PSU-private pairs, counted within each year and summed over the years. This is the Mann-Whitney U statistic of each year, combined |
| Primary test | **Permutation by company**: the ownership labels are shuffled among companies (a company keeps all its years), 10,000 times, two-sided |
| Effect size | Stratified Cliff's delta with a 95% bootstrap interval (companies resampled within ownership type). Positive = PSUs score higher |
| Also reported | Mann-Whitney U, delta and group sizes per year (descriptive, raw p-values) |
| MDE | Simulation: labels shuffled (so no true difference), then a known number of points added to the scores of the "PSU" companies; 500 data sets per shift, each tested with 499 shuffles. Reported in DQS points and as the delta those points produce |
| Effect of practical interest | absolute delta of 0.33 (a "medium" effect by the usual reading of Cliff's delta) |

Sensitivity (not in the BH family): (a) FY2025-26 included; (b) labels shuffled within sector
group only, because PSUs are concentrated in a few sectors.

## How the methods themselves are checked

Before the results are trusted, each test is run on made-up data (pytest):

- **planted effect**: data built with a known effect well above the MDE - the test must find it;
- **no effect**: 500 made-up data sets with no effect - the test must raise a false alarm in
  about 5% of them (accepted range 2.5% to 8.5%, which is what 500 runs can distinguish; for the
  exact tests on counts, which are conservative by construction, the accepted range is 0% to
  8.5%);
- every study must run without error on the synthetic gold tables and on the one-company
  warehouse that CI builds, where it must report "not enough data" and not a number.

## What will not be done

- No test is added, dropped or swapped after the results are seen, without being listed as a
  deviation.
- No filter is changed to move a p-value. A filter that turns out to be impossible (for example
  fewer than 5 companies left) is reported as such.
- No causal claim, in either direction.
- No raw filed value in the published findings: effect sizes, shares, counts and p-values only
  ([publication_policy.md](publication_policy.md)).
