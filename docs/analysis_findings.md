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
4. **A third of companies grew while cutting emissions.** On the balanced panel, 14 of 38
   companies (36.8%) raised turnover and lowered absolute Scope 1+2 emissions; another 11 only
   lowered emissions per rupee; 8 did neither (Q5).
5. **Good disclosure is not associated with a lower carbon intensity.** Among 34 ranked
   companies, 47% sit on the "same side" (better on both, or worse on both) - what chance
   alone would give. A well-made report says the numbers can be trusted, not that they are good
   (Q10).

Two more that matter: the pay-equity gap is **not** narrowing (Q6), and eleven companies report
a work-related death in every one of the four years (Q12).

## SQL techniques used

| Technique | Where |
|---|---|
| Common table expressions with readable names | every question |
| Ratio of sums over a pre-filtered set (numerator and denominator on the same companies) | Q1, Q4, Q6, Q12 |
| `MEDIAN` as an aggregate and as a window function | Q1, Q6, Q8, Q10, Q11 |
| Balanced panel with `HAVING` on per-company counts and `BOOL_OR` | Q1, Q5, Q6 |
| `SEMI JOIN` / `ANTI JOIN` | Q1, Q3 |
| Window functions: `ROW_NUMBER`, `RANK`, running total with an explicit frame | Q2, Q3, Q8, Q9 |
| `LAG` / `LEAD` over a named `WINDOW` | Q3, Q4, Q6, Q8 |
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
and the largest deterioration in GHG intensity, comparability breaks and suspected errors
excluded?

**Answer.** Largest improvements: BEL -74.2% (Asset-heavy), Wipro -52.9% (IT services), Eternal
-48.3% (Consumer), Cipla -21.5% (Healthcare), all from FY2024-25 to FY2025-26. Largest
deteriorations: Tata Consumer +278.7% (Consumer) and Adani Enterprises +62.2% (Asset-heavy),
both from FY2022-23 to FY2023-24; Max Healthcare +3.5% (Healthcare). Two one-year spikes were
set aside (a value 44 times and one 4.6 times its neighbours, both back to normal a year later).

**So what.** The extreme moves sit at the two ends of the window - the first year, where units
were partly inferred, and the latest year, which no later report can confirm yet. They are a
reading list, not a league table: the right next step for each is to open the report. Where
the data is steadier (Healthcare, once its spike is set aside) the largest deterioration is
3.5%.

**Caveat.** The spike screen (a year more than 3 times above or below both neighbours) is a rule
of this analysis, not of the warehouse, and it cannot test a company's first or latest year.
Financials are not ranked on GHG intensity (not material). A turnover swing moves intensity
without any change in emissions.

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

**Answer.** Of the 38 companies in the balanced panel: 14 absolute decoupling (36.8%), 11
relative decoupling (28.9%), 8 no decoupling (21.1%), 5 with falling turnover (13.2%). Absolute
decoupling by sector group: Asset-light 6 of 13, Financials 4 of 10, Asset-heavy 4 of 15.

**So what.** Two thirds of the companies can show a falling intensity, but only one third a
falling footprint. Relative decoupling is what a growing company gets almost for free; absolute
decoupling is what the climate notices. In heavy industry it is the exception (4 of 15), and the
companies outside the panel are the largest emitters.

**Caveat.** Turnover is in current rupees, so part of all "growth" is inflation and decoupling
looks easier than it is. Only two end points are compared: one odd year at either end decides
the class, and a few changes in the panel are implausibly large (they look like filing
differences, not business changes). Scope 1+2 only.

SQL: [q05_decoupling.sql](../analysis/sql/q05_decoupling.sql)

### Q6. Are women a growing part of the workforce, and is the pay gap closing?

**Question.** How did women's share of the workforce and the pay-equity gap move by sector
group, and is the gap narrowing on a balanced panel?

**Answer.** Women in the workforce, whole group, FY2022-23 to FY2025-26: Asset-heavy 5.8% to
7.0%, Asset-light 32.4% to 33.3%, Financials 23.4% to 23.2%. Pay-equity gap (women's share of
wages minus their share of headcount), typical company on the balanced panel, FY2023-24 to
FY2025-26: Asset-light -2.7 to -6.3 points, Financials -4.9 to -5.6, Asset-heavy +0.9 to +1.0;
all 36 companies -2.2 to -2.3. The gap moved closer to zero at 12 of 36 companies (33.3%).

**So what.** The gap is **not narrowing**; in Asset-light it more than doubled. Where women are
a third of the workforce they receive a clearly smaller slice of the wage bill, which points to
where in the hierarchy they work. In heavy industry the gap is near zero, but there women are
about one in fourteen - a small, probably more office-based group. Headcount share alone would have
told a mildly positive story; the wage share turns it around.

**Caveat.** The gap mixes how many women are employed with which roles they hold; it is not
"equal pay for equal work". The wage share exists only from FY2023-24: three years, two steps.
Medians of 10 to 14 companies move when one company moves.

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

**So what.** In this sample disclosure quality is **not associated with** carbon intensity:
knowing that a company reports well tells you nothing about whether it emits little for its
size. That is what the score is designed to be - a measure of how far the numbers can be
trusted - and it is a warning against using reporting quality as a stand-in for performance.

**Caveat.** Descriptive only: 34 companies, one year, a two-by-two table; two or three companies
changing side would change the picture. No causal claim is made in either direction. Financials
are not ranked on GHG intensity and Automobiles had fewer than 5 companies that year. Week 11
tests the relationship properly.

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
that); one owes part of its place to a 74% one-year fall that no later report confirms yet (Q3).

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
- **Disclosure against performance.** 34 companies in one year (Q10).
- **Year-on-year moves.** The first and the latest year cannot be screened for one-year spikes
  (Q3), and the largest moves are exactly there.
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
