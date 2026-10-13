# Analysis findings: twelve business questions

Week 10. Twelve questions answered in SQL on the gold tables (DuckDB), one file each in
[`analysis/sql/`](../analysis/sql/). Data: NIFTY 50 companies plus one, BRSR filings for
FY2022-23 to FY2025-26, 196 company reports. Numbers are from the build of 2026-10-13.

**How to read this page**

- Every figure here is a value we calculate: an intensity, a share, a gap, a median, a count or
  a score. No filed quantity is shown ([publication_policy.md](publication_policy.md)).
- A figure for a group is either the **whole group** (a ratio of sums: all emissions divided by
  all turnover) or the **typical company** (the median). It is never an average of company
  ratios. A group figure is given only for 5 companies or more.
- **Balanced panel** = only companies that filed in every year and had no merger, demerger or
  change of reporting boundary, so the same businesses are compared with themselves.
- This is description, not proof of cause.
- The Disclosure Quality Score is not an ESG rating, and this page is not investment advice.

Run it yourself: `.\scripts\dev.ps1 analysis` writes every result to `data/processed/analysis/`
(local, never committed, because some results hold filed values).

## Executive summary

1. **Five companies carry 85% of the emissions.** In every year the five largest emitters hold
   85.5% to 86.2% of the Scope 1+2 emissions of all companies covered, and ten hold 98.5%. One
   power generator alone is close to half. Any "average" trend of this set is the trend of a
   handful of companies (Q2).
2. **The headline fall in carbon intensity of heavy industry is not like for like.** Across all
   Asset-heavy companies, intensity fell 15.2% in three years. For the 15 companies that can be
   followed without a break, it rose 3.7% - while the typical one of those companies improved by
   38%. Which answer you get depends on who is counted and how (Q1).
3. **Restated figures are common, getting rarer, and not tilted in the companies' favour.** 6.7%
   of the figures that can be checked against the next report were changed materially (14.1%,
   then 5.7%, then 4.0% by year). Of those with a direction, 47.7% make the trend look better -
   a coin toss, not a pattern (Q9).
4. **At least a quarter of companies grew while cutting emissions.** On the balanced panel, 9
   of 38 companies (23.7%) raised turnover and lowered absolute Scope 1+2 emissions, and 9 more
   only lowered emissions per rupee. Another 10 are set aside because their changes are too
   large to accept unread; without that screen the count would have been 14 (Q5).
5. **The biggest year-on-year moves are data problems, not performance.** Every change in GHG
   intensity beyond a factor of two traced back to a first-year unit, a scale slip, a one-year
   reversal or an unconfirmed latest-year figure. Among moves a later report confirms, the
   largest improvement is 40% and the largest deterioration 22% (Q3).

Three more that matter: the pay-equity gap is **not** narrowing - 8 companies moved closer to
zero, 11 away, 17 did not move (Q6); eleven companies report a work-related death in every one of
the four years (Q12); and a simple split shows no visible association between disclosure quality
and carbon intensity - the formal test of Week 11 finds none either, but is too small to rule
one out (Q10).

## SQL techniques used

| Technique | Where |
|---|---|
| Common table expressions with readable names | every question |
| Ratio of sums over a pre-filtered set (numerator and denominator on the same companies) | Q1, Q4, Q6, Q12 |
| `MEDIAN` as an aggregate and as a window function | Q1, Q6, Q8, Q10, Q11 |
| Balanced panel with `HAVING` on per-company counts and `BOOL_OR` | Q1, Q5, Q6 |
| `SEMI JOIN` / `ANTI JOIN` | Q1, Q3 |
| Window functions: `ROW_NUMBER`, `RANK`, running total with an explicit frame | Q2, Q3, Q8, Q9 |
| `LAG` / `LEAD` over a named `WINDOW` | Q3, Q4, Q5, Q6, Q8 |
| Confidence label and plausibility screen with a prioritised `CASE`, `BOOL_OR`, conditional rank | Q3, Q5 |
| `FIRST_VALUE` for change against the first year | Q1, Q6 |
| `QUALIFY` to filter on a window function | Q2, Q3, Q4, Q8, Q9 |
| `PIVOT` (years to columns) and conditional pivot with `MAX(CASE ...)` | Q7; Q1, Q5, Q6 |
| `GROUP BY GROUPING SETS` with `GROUPING()` for labelled subtotals | Q8 |
| Conditional aggregation with `FILTER` | Q2, Q9, Q10, Q11, Q12 |
| Share of a group with `SUM(COUNT(*)) OVER` | Q5, Q10 |
| `UNION ALL` for total rows and for stacking panels | Q1, Q5, Q6, Q7, Q9, Q10, Q12 |
| `STRING_AGG` with `ORDER BY` and `FILTER` | Q1, Q11, Q12 |
| Scalar subqueries for the first, latest or last final year (no hard-coded years) | Q1, Q5, Q9, Q10, Q11 |
| `CASE` for the "5 companies or more" rule on every group statistic | Q1, Q4, Q6, Q7, Q8, Q12 |

## The twelve questions

### Q1. Is each sector group getting less carbon-heavy?

**Question.** How did GHG intensity (Scope 1+2 per Rs crore of turnover) move from FY2022-23 to
FY2025-26 by sector group - as a whole and for the typical company, on all companies and on a
balanced panel?

**Answer.** All companies, whole group: Asset-heavy 293.6 to 248.8 tCO2e per Rs crore
(-15.2%), Asset-light 4.65 to 3.81 (-18.0%), Financials 1.74 to 0.95 (-45.6%). Balanced panel,
whole group: Asset-heavy **+3.7%** (15 companies), Asset-light -14.6% (13), Financials -44.6%
(10). Balanced panel, typical company: Asset-heavy -37.9%, Asset-light -7.0%, Financials -48.2%.

| Sector group | All companies, whole group | Balanced panel, whole group | Difference (composition effect) | Balanced panel, typical company |
|---|---|---|---|---|
| Asset-heavy | -15.2% | +3.7% | -18.9 points | -37.9% |
| Asset-light | -18.0% | -14.6% | -3.5 points | -7.0% |
| Financials | -45.6% | -44.6% | -1.1 points | -48.2% |

**So what.** For Financials and Asset-light the story is the same either way. For Asset-heavy
the two panels **disagree in sign**. The balanced panel leaves out six companies: four whose
reporting boundary changed or that were demerged - among them the largest emitters of the whole
data set - and two that did not file in every year. The headline fall rests on them. And inside the balanced panel the group as a whole
got slightly more intensive while its typical company improved a lot: the smaller companies
improved, the heavy ones did not. "Is heavy industry decarbonising?" has no single honest
number here - quote the panel and the method with it.

**Caveat.** Turnover is the only denominator and is in current rupees, so price rises alone
lower intensity. FY2022-23 units were partly inferred. The balanced panel is the cleaner trend
but a smaller world. Sector groups are broad.

SQL: [q01_decarbonisation.sql](../analysis/sql/q01_decarbonisation.sql)

### Q2. How few companies carry most of the emissions?

**Question.** What share of total Scope 1+2 emissions do the 5 and the 10 largest emitters
hold, each year?

**Answer.** Top 5: 86.2%, 85.8%, 85.5%, 85.5% (FY2022-23 to FY2025-26). Top 10: 98.4% to 98.5%
in every year. The single largest emitter holds 46.5% to 52.2%. Four to five companies make up
80% of the total, six make up 90%.

**So what.** The total of this universe is decided by a power generator, two steel makers, a
cement maker and a refiner. The other 40-odd companies together are under 2%. Engagement,
target-tracking or any "portfolio footprint" should start with those few; for everyone else
intensity and direction matter more than tonnes.

**Caveat.** "Total" is the companies in this project, not India. Scope 1+2 only: the value-chain
emissions of a bank or an oil company are not in it. The concentration barely moved in four
years, which also means it says little about change.

SQL: [q02_emission_concentration.sql](../analysis/sql/q02_emission_concentration.sql)

### Q3. Who moved most on GHG intensity in one year?

**Question.** Within each ranking group, which company had the largest year-on-year improvement
and the largest deterioration in GHG intensity - counting only moves that a later report
confirms?

**Answer.** Each year-on-year pair gets a confidence label. Only **confirmed** pairs are ranked:
for both years the next report repeats Scope 1 and Scope 2 unchanged, and no unit was inferred.
That leaves 20 ranked pairs in three ranking groups (of 99 pairs in all).

| Confirmed pairs only | Company | Ranking group | Years | Intensity (tCO2e per Rs crore) | Change |
|---|---|---|---|---|---|
| Largest improvement | Hindustan Unilever | Consumer | FY2023-24 to FY2024-25 | 0.24 to 0.15 | -40.3% |
| 2nd | Dr. Reddy's | Healthcare | FY2023-24 to FY2024-25 | 15.61 to 10.27 | -34.2% |
| 3rd | BEL | Asset-heavy | FY2023-24 to FY2024-25 | 1.74 to 1.18 | -32.3% |
| Largest deterioration | Asian Paints | Consumer | FY2023-24 to FY2024-25 | 3.16 to 3.86 | +22.2% |
| 2nd | UltraTech Cement | Asset-heavy | FY2023-24 to FY2024-25 | 1,047 to 1,171 | +11.8% |
| 3rd | JSW Steel | Asset-heavy | FY2023-24 to FY2024-25 | 398 to 436 | +9.5% |

Within each ranked group: Asset-heavy BEL (-32.3%) and UltraTech Cement (+11.8%); Consumer
Hindustan Unilever (-40.3%) and Asian Paints (+22.2%); Healthcare Dr. Reddy's (-34.2%), where no
confirmed pair got worse (the smallest improvement is Sun Pharma, -0.9%).

**Unconfirmed - not ranked.** The 79 other pairs, by reason: 36 provisional (they end in
FY2025-26, which no later report confirms yet), 24 with an inferred unit (FY2022-23 emissions
unit not filed, taken from the next report), 7 restated later, 4 one-year reversals, and 8
confirmed pairs in a group with fewer than 5 comparable companies that year. The larger ones
(beyond 30% either way):

| Company | Years | Change | Why it is not ranked |
|---|---|---|---|
| Apollo Hospitals | FY2022-23 to FY2023-24, and back | +359.0%, then -86.9% | one-year reversal |
| Tata Consumer | FY2022-23 to FY2023-24 | +278.7% | inferred unit |
| Eicher Motors | FY2023-24 to FY2024-25, and back | -56.0%, then +200.1% | one-year reversal |
| BEL | FY2024-25 to FY2025-26 | -74.2% | provisional |
| Trent | FY2022-23 to FY2023-24 | +68.3% | restated later |
| Adani Enterprises | FY2022-23 to FY2023-24 | +62.2% | inferred unit |
| Cipla | FY2022-23 to FY2023-24 | +57.0% | inferred unit |
| Wipro | FY2024-25 to FY2025-26 | -52.9% | provisional |
| Adani Enterprises | FY2023-24 to FY2024-25 | +51.5% | restated later |
| Bharti Airtel | FY2024-25 to FY2025-26 | -48.7% | provisional |
| Eternal | FY2024-25 to FY2025-26 | -48.3% | provisional |
| Titan | FY2024-25 to FY2025-26 | -41.5% | provisional |
| Coal India | FY2023-24 to FY2024-25 | +36.5% | confirmed, but only 3 comparable companies in the group |
| TCS | FY2022-23 to FY2023-24 | -35.2% | inferred unit |
| Adani Enterprises | FY2024-25 to FY2025-26 | -33.7% | provisional |
| HCLTech | FY2023-24 to FY2024-25 | -31.4% | confirmed, but only 4 comparable companies in the group |

**What is behind the moves beyond a factor of two.** Each was looked up in the filed data
(unit, scale, boundary, corporate event, restatement). None of them is a confirmed real change.

| Company, year | Move | What the data shows | Verdict |
|---|---|---|---|
| Tata Consumer, FY2022-23 to FY2023-24 | x 3.8 | The FY2022-23 emissions unit was not filed and was inferred. Scope 1 is almost exactly 10 times lower than a year later (x 9.99); energy per rupee also triples in the same step and the renewable share starts at 0%. Same reporting boundary, no corporate event that year. The level then stays where it is for three years. | Data issue in the first-year filing (unit or coverage), not a tripling. Not ranked. |
| Apollo Hospitals, FY2023-24 | x 4.6, then back | Scope 1 is 91 times the year before and falls back to a fiftieth the year after; energy per rupee does the same. The next report repeats the high figure as its comparative, which is why the warehouse's scale-error rule (it compares the two reports) does not see it. | Scale slip in the FY2023-24 filing. Not ranked. |
| Eicher Motors, FY2024-25 | halved, then x 3.0 | Scope 2 falls to 27% and is 7.2 times higher a year later, while energy per rupee is flat in all three years. | Scope 2 of one year is filed on another basis or is wrong. Not ranked. |
| BEL, FY2025-26 | -74% | Scope 2 is filed as zero while about a tenth of the energy is still non-renewable. | Unconfirmed: a zero or a market-based claim. Provisional, not ranked. |
| Wipro, FY2025-26 | -53% | Scope 2 falls to a third as the renewable share rises from 79% to 89%. | Direction plausible, size unconfirmed. Provisional, not ranked. |
| Bajaj Finserv, three years | x 44, then back, then x 9 | Emissions are steady; turnover is filed on a different scale in different years. | Turnover scale problem. Financials are not ranked on GHG. |
| SBI Life, FY2022-23 to FY2023-24 | x 3.0 | First-year unit read from a text field with a gram conversion; Scope 1 jumps 31-fold. | Unit issue in the first-year filing. Not ranked (Financials). |
| Shriram Finance, FY2022-23 to FY2023-24 | -64% | Merger in FY2022-23; the next report restates Scope 1 to less than a tenth. | Corporate event plus restatement. Not ranked (Financials). |
| Jio Financial, BSE, FY2025-26 | -70%, -54% | First years after a demerger; a year of very fast revenue growth. | Provisional. Not ranked (Financials). |

**So what.** Once only confirmed pairs are ranked, the picture is calm: the largest confirmed
improvement is 40% and the largest confirmed deterioration 22%. Every move beyond a factor of
two turned out to be a first-year unit, a scale slip, a one-year reversal or a figure nobody has
confirmed yet. A league table of raw year-on-year changes would have named the companies with
the worst data, not the best or worst performers.

**Caveat.** "Confirmed" means the company repeated the figure a year later, not that the figure
is right; turnover has no comparative in the filings and cannot be confirmed this way. The
largest confirmed improver is itself set aside in Q5, because its emissions fell by more than
half over the three years: confirmed twice by the company, and still worth reading. The
ranking can only cover FY2022-23 to FY2024-25, and mostly its second half. The reversal screen
(a year more than twice, or less than half of, both neighbours) is a rule of this analysis and
cannot test a company's first or latest year. Financials are not ranked on GHG intensity; IT
services, Energy & utilities and Automobiles had fewer than 5 comparable companies. A turnover
swing moves intensity without any change in emissions.

SQL: [q03_ghg_leaders_laggards.sql](../analysis/sql/q03_ghg_leaders_laggards.sql)

### Q4. Which peer groups are switching to renewable energy, and who crossed 50%?

**Question.** How did the renewable share of energy move by peer group, and which companies
went from below half to at least half renewable?

**Answer.** Whole-group share, FY2022-23 to FY2025-26: IT services 44.6% to 68.1%, Consumer
46.5% to 53.3%, Financials 1.7% to 12.4%, Energy & utilities 0.2% to 0.6%; Healthcare 18.8% to
50.1% (from FY2023-24). Nine companies crossed 50%: ITC and Infosys in FY2023-24; BEL, BSE,
Dr. Reddy's and Tata Consumer in FY2024-25; Eicher Motors, Nestle India and Sun Pharma in
FY2025-26.

**So what.** The switch is real where energy is mostly bought electricity (IT, consumer goods,
pharma) and almost absent where energy is the product or the process (power, oil, coal: under
1%). A renewable-share target is cheap for the first kind of company and a different business
for the second, so compare it only inside a peer group.

**Caveat.** Four peer groups (Automobiles until FY2024-25, Cement & construction, Metals &
mining, Industrials & others) have fewer than 5 companies and show no figure. The group share is
weighted by energy, so its biggest user dominates. One crossing goes from 0% to 100% in a year,
which looks like a change in how the figure was filed. Seven energy totals were suspected scale
errors and use the later report's value.

SQL: [q04_renewable_share.sql](../analysis/sql/q04_renewable_share.sql)

### Q5. Who grew while emitting less?

**Question.** Between FY2022-23 and FY2025-26, which companies raised turnover and cut absolute
Scope 1+2 emissions (absolute decoupling), and which only cut emissions per rupee (relative)?

**Answer.** Of the 38 companies in the balanced panel, 10 are set aside as **needs review**:
their turnover or emissions changed by more than -50% or +100% with no recorded corporate event,
or have a one-year reversal. Of the other 28: 9 absolute decoupling, 9 relative decoupling, 6 no
decoupling, 4 with falling turnover.

| Class | Before the screen | After the screen |
|---|---|---|
| Absolute decoupling | 14 (36.8%) | 9 (23.7%) |
| Relative decoupling | 11 | 9 |
| No decoupling | 8 | 6 |
| Turnover fell | 5 | 4 |
| Needs review | - | 10 (26.3%) |

Absolute decoupling after the screen, by sector group: Asset-heavy 3 of 15, Asset-light 3 of 13,
Financials 3 of 10. Five of the 14 companies first counted as absolute decouplers are among those
set aside: four because their emissions fell by more than half, one for a one-year reversal.

**So what.** A safe statement is "at least 9 of 38 companies (about a quarter) grew while
cutting emissions"; the 14 of the unscreened count leaned on the least believable changes. Even
among the plausible cases, as many companies only lowered emissions per rupee as lowered
emissions. Relative decoupling is what a growing company gets almost for free; absolute
decoupling is what the climate notices - and in heavy industry it is 3 of 15, with the largest
emitters outside the panel.

**Caveat.** "Needs review" is not "wrong": a company can really halve its emissions or double
its turnover in three years, and the thresholds are a rule of this analysis. The screened count
is a floor, not an estimate. Turnover is in current rupees, so part of all "growth" is inflation.
Only two end points are compared. Scope 1+2 only.

SQL: [q05_decoupling.sql](../analysis/sql/q05_decoupling.sql)

### Q6. Are women a growing part of the workforce, and is the pay gap closing?

**Question.** How did women's share of the workforce and the pay-equity gap move by sector
group, and is the gap narrowing on a balanced panel?

**Answer.** Women in the workforce, whole group, FY2022-23 to FY2025-26: Asset-heavy 5.8% to
7.0%, Asset-light 32.4% to 33.3%, Financials 23.4% to 23.2%. Pay-equity gap (women's share of
wages minus their share of headcount), typical company on the balanced panel, FY2023-24 to
FY2025-26: Asset-light -2.7 to -6.3 points, Financials -4.9 to -5.6, Asset-heavy +0.9 to +1.0;
all 36 companies -2.2 to -2.3. Company by company (a move of 0.5 points or less counts as
unchanged):

| Sector group | Companies | Gap moved closer to zero | Moved away from zero | Unchanged |
|---|---|---|---|---|
| All | 36 | 8 | 11 | 17 |
| Asset-heavy | 14 | 3 | 4 | 7 |
| Asset-light | 12 | 2 | 3 | 7 |
| Financials | 10 | 3 | 4 | 3 |

**So what.** The gap is **not narrowing**: at about half the companies it did not move, and
among those where it did, more moved away from zero (11) than towards it (8). Where women are
a third of the workforce they receive a clearly smaller slice of the wage bill, which points to
where in the hierarchy they work. In heavy industry the gap is near zero, but there women are
about one in fourteen - a small, probably more office-based group. Headcount share alone would have
told a mildly positive story; the wage share turns it around.

**Caveat.** The gap mixes how many women are employed with which roles they hold; it is not
"equal pay for equal work". The wage share exists only from FY2023-24: three years, two steps.
Medians of 10 to 14 companies move when one company moves: the Asset-light median fell from
-2.7 to -6.3 although only 3 of its 12 companies moved away from zero, so read the counts, not
the median.

SQL: [q06_gender.sql](../analysis/sql/q06_gender.sql)

### Q7. How many companies disclose Scope 3 emissions?

**Question.** What share of companies gives a Scope 3 figure, by sector group and year?

**Answer.** All companies: 78.7%, 72.9%, 78.0%, 78.4% (FY2022-23 to FY2025-26). Financials 90.9%
to 100%; Asset-light 87.5% to 77.8%; Asset-heavy 65.0% to 66.7%.

| Sector group | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| All companies | 78.7% | 72.9% | 78.0% | 78.4% |
| Asset-heavy | 65.0% | 63.2% | 70.0% | 66.7% |
| Asset-light | 87.5% | 70.6% | 72.2% | 77.8% |
| Financials | 90.9% | 91.7% | 100.0% | 100.0% |

**So what.** Voluntary Scope 3 disclosure has stopped spreading: it stands where it stood three
years ago. The companies whose value chain matters most for the climate (heavy industry)
disclose it least, and the companies for whom it is cheapest to report (financials) all do. If
Scope 3 is to become normal practice among large emitters, it will not happen by itself.

**Caveat.** "Disclosed" means a number is in the filing; it says nothing about how many of the
Scope 3 categories are covered, and a filed zero counts. A financial company's figure rarely
includes financed emissions, the part that matters.

SQL: [q07_scope3_adoption.sql](../analysis/sql/q07_scope3_adoption.sql)

### Q8. Where is disclosure quality strongest, and who improved most?

**Question.** What is the typical Disclosure Quality Score (DQS) by sector group and ownership
type, and who improved most from FY2023-24 to FY2024-25?

**Answer.** FY2024-25, typical company: Asset-heavy 87.2, Asset-light 86.0, Financials 84.9;
Government-owned 86.0, private Indian 86.5; all companies 85.7. In FY2022-23 government-owned
companies stood at 75.8 against 87.4 for private Indian ones. Biggest improvers FY2023-24 to
FY2024-25: BSE +14.2 points (67.1 to 81.3), Axis Bank +11.1, Bajaj Finance +10.2, Titan +9.7,
Bajaj Finserv +9.5.

**So what.** Sector and ownership explain almost nothing today: every group sits within three
points of 86. The one real movement is that government-owned companies closed a gap of more
than eleven points in two years. Differences in disclosure quality are between companies, not
between kinds of company, so the score is worth reading per company.

**Caveat.** DQS measures the quality of machine-readable (XBRL) disclosure, not ESG
performance, and it is not an ESG rating. Scores are compared within a year only; the improvers
use the two years built from all four components. FY2025-26 is provisional. MNC subsidiaries
(2 to 3 companies) and most sector-by-ownership cells are too small for a median.

SQL: [q08_disclosure_quality.sql](../analysis/sql/q08_disclosure_quality.sql)

### Q9. How often does last year's number change, and in whose favour?

**Question.** What share of comparable figures is restated materially, by year and by metric,
and how many restatements flatter the trend?

**Answer.** 274 of 4,115 comparable figures (6.7%) were restated materially, at 42 companies:
14.1% of FY2022-23 figures, 5.7% of FY2023-24, 4.0% of FY2024-25. Of the 241 with a direction,
115 (47.7%) make the trend look better. Highest restatement shares among the most-restated
metrics: water consumption 22.4%, Scope 1 emissions 14.9%, waste recovered 14.2%, MSME sourcing
14.1%; most restatements in number: attrition rates (51).

**So what.** One comparable figure in fifteen does not survive a year, and for water and Scope 1
it is one in four to seven: a time series built from first filings alone is wrong often enough
to matter, so use the later report's comparative. There is no sign that companies restate in
their own favour (47.7% is a coin toss). And the falling share suggests reporting is settling
down after the first BRSR years.

**Caveat.** A restatement is a difference between two filings, not a finding of wrongdoing;
correcting a figure is good practice. FY2025-26 is left out because its next report does not
exist yet. FY2022-23 is noisy (inferred units). Suspected scale errors (39) are counted apart.

SQL: [q09_restatements.sql](../analysis/sql/q09_restatements.sql)

### Q10. Do good disclosure and good carbon performance go together?

**Question.** Within each ranking group, how many companies fall in each quadrant of DQS (above
or below the group median) by GHG intensity (better or worse half)?

**Answer.** FY2024-25, 34 companies in five ranking groups: 10 with better disclosure and lower
intensity, 9 with better disclosure and higher intensity, 9 with weaker disclosure and lower
intensity, 6 with weaker disclosure and higher intensity. 47.1% sit on the same side on both.

**So what.** No visible association in this descriptive split; tested formally in Week 11.
The practical reading is a cautious one: the score is built to say how far the numbers can be
trusted, and nothing here gives a reason to use it as a stand-in for performance.

**Formal result (Week 11, Study 1).** Rank correlation between the score and GHG intensity
inside ranking groups, pooled: **rho = -0.02**, 95% interval -0.53 to +0.47, p = 0.93 (24
companies in 4 ranking groups, FY2024-25, confirmed figures only; stratified permutation
test). The null hypothesis of no association is not rejected. The test could only have found a
correlation of 0.68 or more, so this is "cannot tell", not "there is none". Including the
unconfirmed companies (34) gives +0.19, p = 0.30. Details:
[stats_findings.md](stats_findings.md).

**Caveat.** Descriptive only: 34 companies, one year, a two-by-two table; two or three companies
changing side would change the picture. A split like this cannot show that there is no
relationship, and no causal claim is made in either direction. Financials are not ranked on GHG
intensity and Automobiles had fewer than 5 companies that year.

SQL: [q10_dqs_vs_performance.sql](../analysis/sql/q10_dqs_vs_performance.sql)

### Q11. Who is in the top quartile on several environmental measures at once?

**Question.** Which companies are in the top quartile of their ranking group on at least three
of six environmental KPIs in FY2025-26?

**Answer.** 13 of the 39 companies ranked qualify. Four are in the top quartile on five of six:
Tata Motors PV, BEL, Bharti Airtel and Power Grid. Then Eternal and Coal India (four), and Titan,
TCS, Hindustan Unilever, Bajaj Auto, Apollo Hospitals, Dr. Reddy's and IndiGo (three). Every
ranking group has at least one; 11 companies have no top-quartile place at all.

**So what.** Breadth is rarer than a single good number: two thirds of the ranked companies are
not broadly ahead of their peers. The list also shows the limit of "per rupee" comparisons - a
telecom operator and an electronics maker lead a group that also holds steel and cement, and a
power-transmission company leads the utilities. Read it as "ahead of the companies it is ranked
with", not as "clean".

**Caveat.** No financial company can qualify (the six KPIs are not ranked there); IT services
are ranked on three only. Groups have 5 to 11 companies, so "top quartile" can mean first or
second of five. One leader files almost none of the voluntary indicators (Q8's score sees
that); one owes part of its place to a 74% one-year fall that is provisional and rests on a
Scope 2 figure filed as zero (Q3).

SQL: [q11_environmental_leaders.sql](../analysis/sql/q11_environmental_leaders.sql)

### Q12. Where do people die at work, and where more than once?

**Question.** What is the fatality rate per 10,000 people in the workforce by sector group and
year, and which companies report a fatality in two or more years?

**Answer.** Asset-heavy: 0.50, 0.54, 0.61, 0.51 deaths per 10,000 people in the workforce
(FY2022-23 to FY2025-26); Asset-light 0.01 to 0.04; Financials 0.00 to 0.01; all companies 0.18
to 0.24. About two thirds of Asset-heavy companies report at least one death in every year. 16
companies report a fatality in two or more years; 11 of them in all four, every one in
Asset-heavy (metals, cement and construction, energy, ports, telecom).

**So what.** Fatal accidents are not rare events that strike at random: the same eleven
companies report one every single year, and the rate in heavy industry has not come down. For a
board or a lender, "any fatality, again" is a simpler and stronger signal than a
frequency rate that sits next to it in the report.

**Caveat.** Deaths cover employees and workers as the company counts them; contract labour is
included to different degrees. Workforce is a year-end headcount, not hours worked. One accident
can decide a group's rate for a year. A zero can mean a safe year or weak recording.

SQL: [q12_safety.sql](../analysis/sql/q12_safety.sql)

## Where the data was too thin

- **Peer groups.** Four of nine peer groups have fewer than 5 companies, so peer-group figures
  (Q4) exist for five groups only; rankings fall back to the sector group there.
- **Pay equity.** Three years and 10 to 14 companies per sector group (Q6).
- **Disclosure against performance.** 34 companies in one year (Q10); 24 once only confirmed
  figures count, too few to find anything but a very strong association.
- **Year-on-year moves.** Only 20 of 99 pairs are confirmed by a later report and in a group
  with 5 comparable companies (Q3); the first and the latest year cannot be confirmed or
  screened at all, and the largest moves are exactly there.
- **Decoupling.** 10 of 38 panel companies need a look at the report before they can be
  classed (Q5).
- **Restatements of the latest year** are not observable yet (Q9).

## How these numbers are checked

- Every query runs in pytest on synthetic gold tables built from the dbt contracts (made-up
  companies, real column names and types) and must return rows; a second run in CI executes them
  against the warehouse dbt builds from the synthetic filing.
- The headline numbers of Q1 (whole-group and typical-company intensity, all companies) and Q8
  (median score by sector group, by ownership type and overall) are compared with `mf query` on
  the semantic layer: 48 figures, all equal within 1e-9.
- A test reads this page and fails if it contains a filed quantity, an amount in rupees or a
  link to the exchange.
