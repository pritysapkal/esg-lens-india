# Disclosure Quality Score (DQS)

One number from 0 to 100 for each company and financial year. This page describes **version 2**
(2026-10-11); what changed from version 1, and why, is at the end.
Tables: `fct_disclosure_quality` (scores), `int_dqs_components` (the counts behind them, local
only), `rpt_public_disclosure_quality` (the public copy).

## What it measures - and what it does not

**It measures how well a company discloses**: did it file what it had to, how much of the
voluntary part did it also answer, do the numbers inside one report agree with each other, do they
still stand in the next report, and how far did an independent party check them.

**It does not measure ESG performance.** A company with very high emissions that reports them
completely, consistently and with full assurance scores high. A company with low emissions and a
thin or sloppy report scores low. The score says how much is disclosed and how far it can be
trusted, not whether the numbers are good.

It is also **not an ESG rating, not a finding of wrongdoing and not investment advice**.

**Compare scores only within one financial year.** The years are built from different parts (see
"Re-weighting"), so a company's score in FY2025-26 is not comparable with its score in FY2023-24.
Ranks and percentiles are always within a ranking group *and* a year.

## Regulatory context

- **BRSR** (SEBI circular SEBI/HO/CFD/CMD-2/P/CIR/2021/562, 10 May 2021) has two kinds of
  indicators under each of its nine principles: **Essential** (mandatory, about 98) and
  **Leadership** (voluntary, about 42).
- **BRSR Core** (SEBI circular of 12 July 2023): a subset of indicators on which the top 150
  listed companies must obtain **reasonable assurance from FY2023-24**. Every company in this
  project (NIFTY 50) is inside the top 150. So for this universe, reasonable assurance on the
  Core is **compliance, not a sign of quality**.
- **SEBI circular of 28 March 2025**: a company may obtain an **"assessment"** by a third party,
  against the standards of the Industry Standards Forum (ASSOCHAM, CII, FICCI), instead of
  assurance. The filings carry this choice from FY2024-25.

These three facts shape version 2: what is mandatory tells little apart, so the score now also
looks at what is voluntary - Leadership indicators and assurance beyond the Core.

## The formula

```
DQS = 100 x  sum(weight x component)  /  sum(weight)      over the components that could be scored
```

| Component | Weight | In one line |
|---|---|---|
| Completeness | 0.30 | half mandatory completeness, half voluntary depth |
| Internal consistency | 0.30 | 1 - failed checks / applicable checks, inside one filing |
| Temporal consistency | 0.20 | 1 - flagged metrics / comparable metrics, against the next report |
| Assurance | 0.20 | baseline for the level obtained + bonus when the whole report is covered |

Each component is a number between 0 and 1. The weights are in the seed `dqs_weights.csv` (a test
checks that they add up to 1); the assurance points are in `dqs_assurance_points.csv`. The total
is rounded to one decimal. Weights and grade cut-offs are the same as in version 1.

**Grades:** A = 85 and above, B = 70 to below 85, C = 55 to below 70, D = below 55. A grade needs
**at least three components**; with two, the total is shown and the grade is
`insufficient_data`.

**Rank and percentile** are given within the company's ranking group and financial year, only for
scores with at least three components, and only when at least 5 companies of the group have such
a score that year. Rank 1 and percentile 100 are the best; ties share the better rank.

**`is_provisional`** is true when the temporal check could not be run because no later filing
exists yet. That is every score of the latest year: it can still fall when the next report comes.

Every component is a **rate, not a count**: a company that files more is not punished for having
more things that can go wrong.

## The four components

### 1. Completeness (weight 0.30) = two halves

`completeness = (mandatory_completeness + voluntary_depth) / 2`

#### 1a. Mandatory completeness (half)

`required metrics filed / required metrics for that year`

- *Required* comes from `metric_disclosure_requirement.csv`: 6 essential metrics from FY2022-23
  (turnover, headcount, attrition, women on the board, NIC code, reporting boundary), and the BRSR
  Core metrics from FY2023-24. Scope 3 is voluntary and never counts here.
- A metric is only required if the taxonomy of that filing has a field for it (31 metrics with
  the FY2023-24 taxonomy, 33 with the later ones).
- A metric filed as **"NA" / not applicable counts as disclosed** here: the company answered a
  mandatory question. A metric with no fact at all, or an empty (nil) one, does not.

#### 1b. Voluntary depth (half)

`Leadership indicators with a substantive value / Leadership indicators in the taxonomy of the filing`

**How Leadership indicators are identified.** Nothing is guessed from names. In the presentation
linkbase of every SEBI taxonomy version, each of the nine Principle sections has a heading element
`LeadershipIndicatorsAbstract`. Everything under that heading is a Leadership element. One
*indicator* is one direct child of the heading (a question, or the heading of a table) with all
the elements below it. `scripts/build_leadership_map.py` reads the taxonomy and writes the seed
`leadership_indicator_map.csv`:

| Taxonomy version | Used by | Leadership indicators | Reportable elements |
|---|---|---|---|
| 2021-09-30 | FY2022-23 | 47 | 157 |
| 2023-06-30 | FY2022-23 | 47 | 157 |
| 2024-04-30 | FY2023-24 | 44 | 122 |
| 2025-05-31 | FY2024-25 | 45 | 124 |
| 2026-02-28 | FY2025-26 | 45 | 124 |

The taxonomy has a few more indicators than SEBI's numbered list (about 42) because it files some
numbered indicators in parts (for example life insurance for employees and for workers
separately). Left out of the count: headings, tables, axes and members; the free "Notes" block of
a principle; the elements in which a company says that an indicator does not apply to it (a
"not applicable" explanation or an "is this applicable" yes / no flag); and the assurance
bookkeeping elements. Every indicator in the seed has facts in the filings of its taxonomy
version.

**What counts as a substantive value.** At least one element of the indicator has, for the
reporting year:

- a **number** (a zero counts - "0 complaints" is an answer), or
- a **text** that is not empty and is not "NA", "N/A", "Not applicable", "Not available", "-",
  "Nil" or "None". A plain "Yes" or "No" counts.

All parsed facts are used (about 400,000 facts and 20,000 long texts), not only the 34 catalogue
metrics. Note the difference with 1a: for a *mandatory* metric "NA" is an answer; for a
*voluntary* indicator "NA" means the company did not go further, so it earns nothing.

*Example:* Reliance, FY2023-24: 40 of 44 Leadership indicators have a substantive value, so
voluntary depth = 0.91. Tata Consumer, same year: 0 of 44. Reliance filed 30 of its 31 mandatory
metrics, Tata Consumer all 31 - on mandatory completeness alone Tata Consumer would be ahead.

**Per-indicator disclosure rates** (`dbt/analyses/dqs_leadership_disclosure_rates.sql`, all four
years together; 50 indicator names, because a few were renamed or dropped between versions). The
median indicator is disclosed by 81% of company-years; 13 indicators are above 90% and 8 are
below 50%. The most and least disclosed:

| Leadership indicator | Principle | Disclosed by |
|---|---|---|
| Life insurance or compensatory package on death (one of its two parts) | 3 | 95.4% |
| Processes to manage conflicts of interest of board members | 1 | 94.4% |
| Web link to information on products and services | 9 | 93.9% |
| Business continuity and disaster management plan | 6 | 92.9% |
| ... | | |
| Benefits shared from intellectual property based on traditional knowledge | 8 | 16.8% |
| Other assessments of value-chain partners (human rights) | 5 | 9.7% |
| Actions to mitigate negative social impacts found in impact assessments | 8 | 7.7% |
| Corrective actions after an adverse order in an intellectual-property dispute | 8 | 2.6% |

**Indicators that carry no information** (everybody or nobody discloses them, so they cannot
tell two companies apart): over all four years together there is **none**, and no indicator is
disclosed by 100% in any year. Within single years two are disclosed by nobody:

| Year | Indicator | Disclosed by |
|---|---|---|
| FY2024-25 | Corrective actions after an adverse intellectual-property order (P8) | 0 of 50 |
| FY2025-26 | Actions to mitigate negative social impacts (P8) | 0 of 51 |

Both describe an event that most companies simply did not have. They are kept in the count
(removing them would be tuning); they lower every company of that year by the same 1 / 45.

### 2. Internal consistency (weight 0.30)

`1 - failed checks / applicable checks`, using only the one filing. Unchanged from version 1.

| Check | Applies when | Fails when |
|---|---|---|
| Waste balance | generated, recovered and disposed are all filed | generated - recovered - disposed is more than 20% of generated (either way) |
| Waste recovery | generated and recovered are filed | recovered is more than generated |
| Implausible zero (4 checks) | the value is filed and a zero cannot be right | 0% of wages to women with women on the payroll; zero energy or zero water at a non-financial company; zero headcount |
| Units | always | a current-year value needed a scale correction (turnover in crore instead of rupees), an approved manual override, or its text unit contradicts the next filing |

A check that cannot be run (for example a bank with no waste figures) is left out of both the top
and the bottom of the fraction.

**Not a failed check:** a filed intensity that uses another denominator than "per rupee" (per
crore, per lakh). That is a difference of basis, not a mistake by the company.

*Example:* Titan, FY2022-23. Six checks apply. Two fail: the waste figures do not add up, and a
unit had to be corrected. Internal consistency = 1 - 2 / 6 = 0.67.

### 3. Temporal consistency (weight 0.20)

`1 - flagged metrics / comparable metrics`. Unchanged from version 1.

A metric is *comparable* when the company's next report repeats the same year's value as a
comparative (see [restatement_method.md](restatement_method.md)). A comparable metric is *flagged*
when, in the order below, the first one applies:

1. **suspected scale error** - the two values are more than 100 times apart (10 times for a
   percentage), or exactly a power of ten apart;
2. **material restatement** - the later report changes the value by more than 5% (and more than
   1 percentage point for a percentage, at least 2 units for a count), and no merger, demerger or
   change of reporting boundary explains it;
3. **unexplained year-on-year jump** - turnover or headcount moves by more than 40% against the
   previous year with no corporate event or boundary change on record (`int_yoy_anomalies`).

Each metric is counted once. Scale errors are counted here and only here.

**Empty when there is no later filing** - always for the latest year (FY2025-26). The component
is left empty, not set to 1 or 0, and the score is marked `is_provisional`.

*Example:* Coal India, FY2022-23. 12 metrics could be compared with the FY2023-24 report. Eight
were more than 100 times apart, one more was restated materially. Temporal consistency =
1 - 9 / 12 = 0.25.

### 4. Assurance (weight 0.20): beyond compliance

`assurance = baseline of the level obtained + 0.5 if the whole report is covered (at most 1)`

| What the filing reports | Points | Why |
|---|---|---|
| Reasonable assurance (on the Core) | 0.5 | Required by SEBI for these companies: the compliance baseline, so only half the points |
| Third-party **assessment** instead of assurance | 0.4 | Allowed since the March 2025 circular; a lighter check than assurance, so a little below the baseline |
| Limited assurance only | 0.3 | Below what SEBI requires for the Core |
| Nothing marked as assured | 0.0 | |
| **+ whole report covered** (type "All") | + 0.5 | The company had more than the Core checked: this is the voluntary part |

**Values actually found in the filings** (inspected before the rule was written):

| Field in the filing | Years | Values |
|---|---|---|
| Whether assessment or assurance of the Core was undertaken | FY2024-25, FY2025-26 | "Yes assurance" (95), "Yes assessment" (5) |
| Type of assessment or assurance obtained | FY2024-25, FY2025-26 | "All" (28), "Partial" (72) |
| Whether reasonable assurance of the Core was undertaken | FY2023-24 | true (47), false (1) |
| Assurance sub-type, per disclosure | FY2023-24 onward | "Reasonable", "Limited" |
| Type of assurance, per section (30 sections) | FY2023-24 onward | "All", "Partial" |

How they are read:

- **Level**: "assessment" if the company states "Yes assessment"; otherwise "reasonable" if at
  least one disclosure is marked Reasonable, "limited" if only Limited marks exist,
  "not_disclosed" if nothing is marked.
- **Whole report**: the filed type is "All". FY2023-24 has no such field, so there the rule is
  "every one of the 30 sections is marked All". In FY2024-25 and FY2025-26, where both exist,
  the two agree for every company (14 of 14 in each year), which is why the same rule is safe
  for FY2023-24.
- **FY2022-23 stays empty**: the report had no place to state assurance.

| Year | Reasonable + whole report (1.0) | Reasonable, Core only (0.5) | Assessment (0.4) | Nothing (0.0) |
|---|---|---|---|---|
| FY2023-24 | 11 | 36 | - | 1 |
| FY2024-25 | 14 | 33 | 3 | 0 |
| FY2025-26 | 14 | 35 | 2 | 0 |

No company-year has limited assurance only. Assurance is still what the company states in its
own filing; we do not read the assurance statement.

## Re-weighting when a component is empty

When a component cannot be scored, its weight is shared out over the others in proportion; the
company is not given a free 1 or an unfair 0. `dqs_components_used` says how many were used.

| Case | Components used | Weights after re-weighting |
|---|---|---|
| FY2023-24, FY2024-25 | all four | 0.30 / 0.30 / 0.20 / 0.20 |
| FY2025-26 (no temporal check, provisional) | three | 0.375 / 0.375 / - / 0.25 |
| FY2022-23 (no assurance field) | three | 0.375 / 0.375 / 0.25 / - |
| Two components only | two | total shown, grade `insufficient_data`, no rank |

This is why scores are compared only within a year: FY2022-23 has no assurance component (which
now costs most companies points), and FY2025-26 has no temporal component (the main source of
lost points in other years).

*Example:* a FY2025-26 company that filed every mandatory metric and 6 in 10 Leadership
indicators (completeness 0.8), passed every internal check and has Core assurance only (0.5):
(0.30 x 0.8 + 0.30 x 1 + 0.20 x 0.5) / 0.80 = 0.80, so DQS = 80.0, provisional. This is one of
the unit tests.

## Reason codes

`dqs_reason_codes` names up to three reasons for the lost points, the largest loss first:
`missing_required_metrics`, `low_voluntary_disclosure`, `waste_balance_gap`,
`waste_recovery_over_100`, `implausible_zero`, `unit_inconsistency`, `suspected_scale_error`,
`material_restatement`, `unexplained_yoy_anomaly`, `assurance_core_only`,
`assessment_not_assurance`, `limited_assurance`, `no_assurance`.

## Results (196 company-years, build of 2026-10-11)

| | Version 1 | Version 2 |
|---|---|---|
| Lowest / median / highest | 68.8 / 98.25 / 100 | 63.4 / 85.0 / 99.6 |
| Middle half of the scores | 93.5 to 100 | 80.2 to 89.6 |
| Grade A / B / C / D | 187 / 8 / 1 / 0 | 98 / 90 / 7 / 0 |
| `insufficient_data` | - | 1 |
| Exactly 100 | 75 | 0 |
| Ranked within group and year | 185 | 185 |

| Financial year | n | Mean | Median | Lowest | Highest | A / B / C | Components |
|---|---|---|---|---|---|---|---|
| FY2022-23 | 47 | 85.5 | 85.8 | 65.2 | 99.6 | 25 / 19 / 2 | 3 (no assurance); one company-year with two |
| FY2023-24 | 48 | 84.4 | 85.9 | 67.1 | 98.2 | 26 / 19 / 3 | 4 |
| FY2024-25 | 50 | 85.8 | 85.65 | 68.7 | 97.9 | 28 / 21 / 1 | 4 |
| FY2025-26 | 51 | 83.8 | 82.9 | 63.4 | 97.9 | 19 / 31 / 1 | 3 (provisional) |

| Sector group | n | Mean | Median | Mean voluntary depth |
|---|---|---|---|---|
| Asset-heavy | 80 | 84.9 | 85.5 | 0.71 |
| Asset-light | 69 | 85.2 | 85.8 | 0.74 |
| Financials | 47 | 84.3 | 83.1 | 0.69 |

Most often named reasons: `low_voluntary_disclosure` (185 company-years), `assurance_core_only`
(104), `material_restatement` (64), `unit_inconsistency` (29), `waste_balance_gap` (28).

**Finding - still clustered, and we leave it so.** Version 2 no longer piles up at 100, and A and
B are now about even. But the scores still sit in a narrow band: 101 of 196 lie between 80 and
90, and there is no grade D. This is a property of the universe, not of the cut-offs: NIFTY 50
companies file nearly everything that is mandatory, two thirds of them answer 70% to 90% of the
Leadership indicators, and two thirds have exactly the required Core assurance. The cut-offs and
weights were not moved to spread the grades.

## Sensitivity to the weights

All companies of a year are ranked twice: with the weights above and with four equal weights of
0.25 (`dbt/analyses/dqs_weight_sensitivity.sql`).

| Financial year | Companies | Spearman rank correlation | Moving 5 ranks or more | Largest move |
|---|---|---|---|---|
| FY2022-23 | 47 | 0.988 | 2 | 5 |
| FY2023-24 | 48 | 0.982 | 1 | 16 |
| FY2024-25 | 50 | 0.990 | 2 | 7 |
| FY2025-26 | 51 | 0.989 | 2 | 14 |
| All years | 196 | 0.987 | 7 | 16 |

The ranking hardly depends on the weights: correlation 0.99, and 7 of 196 company-years move by
five places or more (version 1: 0.990 and 10). The scores themselves differ by 1.8 points on
average.

## Limitations

- **Clustered scores** (see the finding above). Read the components and the reason codes, not
  only the total.
- **Some Leadership indicators do not apply to every sector.** A bank has no products to reclaim
  at end of life and no plants in water-stressed areas; its honest answer is "Not applicable",
  which earns nothing. Financials average 0.69 voluntary depth against 0.71 and 0.74 for the
  other sector groups. The effect is softened, not removed, by ranking within the ranking group:
  a bank is ranked against other financial companies, who face the same indicators.
- **Voluntary depth counts presence, not quality.** A zero, a "No" or a short sentence counts as
  much as a full table.
- **A few companies file almost no Leadership indicator in the XBRL file** (Tata Consumer from
  FY2023-24, Power Grid in all four years: 0 to 2 of 45). Their printed report may say more; the
  score reads only the filed data.
- **Each indicator and each required metric has the same weight.**
- **Assurance is self-reported.** The level and the scope are what the company marks in its own
  filing. The points (0.5 / 0.4 / 0.3 / +0.5) are a judgement, written down so it can be argued
  with.
- **Years are not comparable** (different components), and the latest year is provisional: expect
  FY2025-26 scores to fall when the FY2026-27 reports arrive.
- **FY2022-23 is noisy**: units were inferred and most scale errors are in that year.
- **A restatement is not wrongdoing.** Correcting a figure is good practice; the score only records
  that the first figure did not hold.
- **Internal checks are few** (four to seven per filing) and lean on waste: one failed check costs
  a seventh to a quarter of that component.
- **Small groups**: no rank when fewer than 5 companies of the ranking group have a gradable score
  that year (Automobiles in three of the four years).
- **The weights are a judgement**, not an estimate. The sensitivity check shows the ranking does
  not hang on them.

## Publication

The total, the component scores (including the two halves of completeness), the grade, the rank,
the percentile, the provisional flag, the assurance level and scope and the reason codes are
values we calculate, so they are public ([publication_policy.md](publication_policy.md)); they
are in `rpt_public_disclosure_quality` and in the KPI catalogue with `public_safe = true`. The
counts behind the components (how many metrics, which ones are missing, which Leadership
indicators a company answered) stay in `int_dqs_components` and
`int_dqs_leadership_disclosure` and are not published.

Every published score carries the note: **the Disclosure Quality Score is not an ESG rating and
nothing here is investment advice.**

## Version 1 to version 2: what changed and why

Version 1 did not tell companies apart: 187 of 196 company-years were grade A and 75 scored
exactly 100. The reason was *what* it measured - things that are mandatory for every company in
this universe. Version 2 changes what is measured; it does not change the weights or the
cut-offs.

| | Version 1 | Version 2 | Why |
|---|---|---|---|
| Completeness | mandatory metrics only | half mandatory, half **voluntary depth** (Leadership indicators) | 176 of 196 company-years filed every mandatory metric; the voluntary part is where reports differ |
| Assurance | reasonable = 1.0 | reasonable on the Core = **0.5**; whole report = **+0.5**; assessment = 0.4; limited = 0.3 | Core assurance is required by SEBI for the top 150, so all but one company-year scored 1.0; only going beyond it shows quality |
| Assurance level | Reasonable / Limited marks | the same, plus the company's own statement "assessment" (March 2025 circular) and the scope All / Partial | The scope was left unused in version 1 |
| Grade | with two components or more | needs **three**; otherwise `insufficient_data` | A grade from two components (one company-year) says too little |
| Rank, percentile | within ranking group and year | the same, only for gradable scores | Made explicit; years are not comparable |
| Latest year | scored like any other | flagged **`is_provisional`** | Its restatements are not known yet |
| Internal and temporal consistency | - | unchanged | |
| Weights, grade cut-offs | 0.30 / 0.30 / 0.20 / 0.20; 85 / 70 / 55 | unchanged | The fix is in what is measured, not in tuning |
