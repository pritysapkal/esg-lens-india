# Disclosure Quality Score (DQS)

One number from 0 to 100 for each company and financial year. Built in Week 8, lean scope.
Tables: `fct_disclosure_quality` (scores), `int_dqs_components` (the counts behind them, local
only), `rpt_public_disclosure_quality` (the public copy).

## What it measures - and what it does not

**It measures how well a company discloses**: did it file what it had to, do the numbers inside
one report agree with each other, do they still stand in the next report, and did someone
independent check them.

**It does not measure ESG performance.** A company with very high emissions that reports them
completely, consistently and with assurance scores 100. A company with low emissions and a sloppy
report scores low. The score says how far the numbers can be trusted, not whether they are good.

It is also **not an ESG rating, not a finding of wrongdoing and not investment advice**. A low
score means "check this report before using its numbers".

## The formula

```
DQS = 100 x  sum(weight x component)  /  sum(weight)      over the components that could be scored
```

| Component | Weight | In one line |
|---|---|---|
| Completeness | 0.30 | required metrics filed / required metrics |
| Internal consistency | 0.30 | 1 - failed checks / applicable checks, inside one filing |
| Temporal consistency | 0.20 | 1 - flagged metrics / comparable metrics, against the next report |
| Assurance | 0.20 | points for the assurance level |

Each component is a number between 0 and 1. The weights are in the seed `dqs_weights.csv` (a test
checks that they add up to 1); the assurance points are in `dqs_assurance_points.csv`. The total
is rounded to one decimal.

**Grades:** A = 85 and above, B = 70 to below 85, C = 55 to below 70, D = below 55.

**Rank and percentile** are given within the company's ranking group and year, and only when at
least 5 companies in that group have a score that year - the same rule as for the KPI percentiles.
Rank 1 and percentile 100 are the best; ties share the better rank.

Every component is a **rate, not a count**: a company that files more is not punished for having
more things that can go wrong.

## The four components

### 1. Completeness (weight 0.30)

`required metrics filed / required metrics for that year`

- *Required* comes from `metric_disclosure_requirement.csv`: 6 essential metrics from FY2022-23
  (turnover, headcount, attrition, women on the board, NIC code, reporting boundary), and the BRSR
  Core metrics from FY2023-24. Scope 3 is voluntary and never counts.
- A metric is only required if the taxonomy of that filing has a field for it. The two assurance
  fields entered the taxonomy in FY2024-25, so they are required from then (31 metrics with
  the FY2023-24 taxonomy, 33 with the later ones).
- A metric filed as **"NA" / not applicable counts as disclosed**. A metric with no fact at all,
  or an empty (nil) one, does not.
- Each required metric counts the same.

*Example:* BSE, FY2023-24. 31 metrics were required; 28 were filed. The POSH complaint rate and
the two related-party shares are missing. Completeness = 28 / 31 = 0.90.

### 2. Internal consistency (weight 0.30)

`1 - failed checks / applicable checks`, using only the one filing.

| Check | Applies when | Fails when |
|---|---|---|
| Waste balance | generated, recovered and disposed are all filed | generated - recovered - disposed is more than 20% of generated (either way) |
| Waste recovery | generated and recovered are filed | recovered is more than generated |
| Implausible zero (4 checks) | the value is filed and a zero cannot be right | 0% of wages to women with women on the payroll; zero energy or zero water at a non-financial company; zero headcount |
| Units | always | a current-year value needed a scale correction (turnover in crore instead of rupees), an approved manual override, or its text unit contradicts the next filing |

A check that cannot be run (for example a bank with no waste figures) is left out of both the top
and the bottom of the fraction.

**Not a failed check:** a filed intensity that uses another denominator than "per rupee" (per
crore, per lakh). That is a difference of basis, not a mistake by the company; it is shown in
`ghg_intensity_filed_basis` and costs no points.

*Example:* Titan, FY2022-23. Six checks apply. Two fail: the waste figures do not add up, and a
unit had to be corrected. Internal consistency = 1 - 2 / 6 = 0.67.

### 3. Temporal consistency (weight 0.20)

`1 - flagged metrics / comparable metrics`

A metric is *comparable* when the company's next report repeats the same year's value as a
comparative (see [restatement_method.md](restatement_method.md)). A comparable metric is *flagged*
when, in the order below, the first one applies:

1. **suspected scale error** - the two values are more than 100 times apart (10 times for a
   percentage), or exactly a power of ten apart;
2. **material restatement** - the later report changes the value by more than 5% (and more than
   1 percentage point for a percentage, at least 2 units for a count), and no merger, demerger or change of
   reporting boundary explains it. A restatement that the filing mentions in a note still counts:
   the first number was still wrong;
3. **unexplained year-on-year jump** - turnover or headcount moves by more than 40% against the
   previous year with no corporate event or boundary change on record (`int_yoy_anomalies`).

Each metric is counted once, however many of its breakdowns are affected. Pairs whose unit had to
be taken from the later filing are not comparable (the test would be circular).

**Scale errors are counted here and only here.** The value replaced in the KPIs
(`scale_error_values_replaced`) is the same event, so it is not also an internal check.

**Empty when there is no later filing.** The latest year (FY2025-26) has no next report, so
nothing can be tested and the component is left empty, not set to 1 or 0. The same holds for a
company whose following year is not in the data. Year-on-year jumps of the latest year stay in
`int_yoy_anomalies` but do not enter the score.

*Example:* Coal India, FY2022-23. 12 metrics could be compared with the FY2023-24 report. Eight
were more than 100 times apart, one more was restated materially. Temporal consistency =
1 - 9 / 12 = 0.25.

### 4. Assurance (weight 0.20)

| Level | Points | Meaning |
|---|---|---|
| reasonable | 1.0 | at least one disclosure is marked as assured at the Reasonable level |
| limited | 0.6 | disclosures are marked as assured at the Limited level only |
| none / not_disclosed | 0.0 | the filing marks no disclosure as assured |

The level is read from the filing itself: from FY2023-24 each section of the report can carry a
mark "Reasonable" or "Limited". The highest level found is used; a company is not marked down for
adding limited assurance on other sections. The existing column `assurance_type` (All / Partial)
is the *scope* of the assurance, not its level, so it is not used here.

**Empty for FY2022-23**: BRSR Core and its assurance did not exist yet and the report had no place
to state it.

*Example:* BSE, FY2023-24 marks no section as assured: 0 points. Every other company-year from
FY2023-24 on has at least its Core sections at the Reasonable level: 1 point.

## Re-weighting when a component is empty

When a component cannot be scored, its weight is shared out over the others in proportion; the
company is not given a free 1 or an unfair 0. `dqs_components_used` says how many were used. With
fewer than two components there is no score.

| Case | Components used | Weights after re-weighting |
|---|---|---|
| FY2023-24, FY2024-25 | all four | 0.30 / 0.30 / 0.20 / 0.20 |
| FY2025-26 (no temporal check) | three | 0.375 / 0.375 / - / 0.25 |
| FY2022-23 (no assurance field) | three | 0.375 / 0.375 / 0.25 / - |

*Example:* a FY2025-26 company with completeness 0.6, internal consistency 1 and limited assurance
(0.6): (0.30 x 0.6 + 0.30 x 1 + 0.20 x 0.6) / 0.80 = 0.75, so DQS = 75.0. This is one of the three
unit tests of the model; the other two are the perfect company (100) and the company that only
lacks assurance (80).

## Reason codes

`dqs_reason_codes` names up to three reasons for the lost points, the largest loss first:
`missing_required_metrics`, `waste_balance_gap`, `waste_recovery_over_100`, `implausible_zero`,
`unit_inconsistency`, `suspected_scale_error`, `material_restatement`,
`unexplained_yoy_anomaly`, `limited_assurance`, `no_assurance`. Empty means a score of 100.

## Results (196 company-years, build of 2026-10-11)

| | |
|---|---|
| Lowest / median / highest | 68.8 / 98.25 / 100 |
| Grade A / B / C / D | 187 / 8 / 1 / 0 |
| Exactly 100 | 75 |
| Ranked within a group | 185 (Automobiles has fewer than 5 companies in three years) |

| Financial year | Mean | Median | Lowest | Components |
|---|---|---|---|---|
| FY2022-23 | 90.8 | 90.2 | 68.8 | 3 (no assurance) |
| FY2023-24 | 96.3 | 99.0 | 70.8 | 4 |
| FY2024-25 | 97.1 | 99.1 | 85.5 | 4 |
| FY2025-26 | 98.1 | 100.0 | 89.3 | 3 (no temporal check) |

Most often named reason: `material_restatement` (74 company-years), then `unit_inconsistency`
(32), `waste_balance_gap` (28) and `missing_required_metrics` (20).

## Sensitivity to the weights

Question: would the ranking change if all four weights were 0.25? All companies of a year are
ranked twice, once with each set of weights (`dbt/analyses/dqs_weight_sensitivity.sql`).

| Financial year | Companies | Spearman rank correlation | Moving 5 ranks or more | Largest move |
|---|---|---|---|---|
| FY2022-23 | 47 | 0.987 | 6 | 5 |
| FY2023-24 | 48 | 0.986 | 2 | 10 |
| FY2024-25 | 50 | 0.990 | 2 | 7 |
| FY2025-26 | 51 | 1.000 | 0 | 0 |
| All years | 196 | 0.990 | 10 | 10 |

The ranking hardly depends on the weights: the correlation is 0.99 and 10 of 196 company-years
move by five places or more. In FY2025-26 nothing moves at all, because completeness and internal
consistency have the same weight under both sets and assurance is the same for every company.
The scores themselves differ by 0.7 points on average.

## Limitations

- **The score sits near the top.** 187 of 196 company-years are grade A and 75 score exactly 100.
  The universe is the NIFTY 50: large companies that file almost everything. The score separates
  the weak reports from the rest; it does not rank the good ones finely. Read the components and
  the reason codes, not only the total.
- **Each required metric has the same weight** in completeness. A missing Scope 1 figure costs as
  much as a missing related-party share.
- **Assurance is self-reported and almost constant.** The level is what the company marks in its
  own filing; we do not read the assurance statement. From FY2023-24 on, all company-years but
  one report reasonable assurance, so this component adds very little information today.
- **The latest year has no temporal check**, and FY2022-23 has no assurance component. Scores of
  different years are therefore built from different parts: FY2025-26 looks best partly because
  its restatements are not known yet. Compare companies within a year, not a company's score
  across years, and expect FY2025-26 scores to fall when the FY2026-27 reports arrive.
- **FY2022-23 is noisy**: units were inferred and most scale errors are in that year, so its
  temporal scores are the lowest.
- **A restatement is not wrongdoing.** Correcting a figure is good practice; the score only records
  that the first figure did not hold.
- **Internal checks are few** (four to seven per filing) and lean on waste: one failed check costs
  a seventh to a quarter of that component.
- **Small groups**: no rank is given when fewer than 5 companies of the ranking group have a score
  that year.
- **The weights are a judgement**, not an estimate. The sensitivity check shows the ranking does
  not hang on them.

## Publication

The total, the four component scores, the grade, the rank, the percentile and the reason codes are
values we calculate, so they are public ([publication_policy.md](publication_policy.md)); they are
in `rpt_public_disclosure_quality` and in the KPI catalogue with `public_safe = true`. The counts
behind the components (how many metrics, which ones are missing, how many checks failed) stay in
`int_dqs_components` and are not published.

Every published score carries the note: **the Disclosure Quality Score is not an ESG rating and
nothing here is investment advice.**
