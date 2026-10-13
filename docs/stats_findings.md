# Statistics findings: five studies

Week 11. Five questions put to a formal test. What was tested, on which data and with which
decision rule was written down and committed **before** any result was computed:
[stats_hypotheses.md](stats_hypotheses.md). Data: NIFTY 50 companies plus one, BRSR filings
for FY2022-23 to FY2025-26. Numbers are from the build of 2026-10-13.

- Every figure here is one we calculate: a correlation, a share, a median change, an odds
  ratio, a count or a p-value. No filed quantity is shown
  ([publication_policy.md](publication_policy.md)).
- These are associations in a small set of companies. Nothing here says that one thing
  produces another.
- The Disclosure Quality Score (DQS) is not an ESG rating, and this page is not investment advice.

Run it yourself: `.\scripts\dev.ps1 stats` (about one minute; results in
`data/processed/stats/`, local). Code: [`analysis/stats/`](../analysis/stats/).

## The result in five lines

**None of the eight primary tests rejects its null hypothesis** once the eight are corrected
for being eight. Four of the five studies are too small to find anything but a large effect,
and the page says so each time.

| Study | Question | Answer in one line |
|---|---|---|
| 1 | Do companies that disclose better have a lower carbon intensity? | No association found (rho -0.02), but with 24 companies only a very strong one could have been found |
| 2 | Did carbon intensity fall from FY2023-24 to FY2024-25? | The typical company fell 9%; that clears the 5% bar on its own (p = 0.015) but not after correction (p = 0.12) |
| 3 | Do restatements flatter the trend? | No: 47.7%, a coin toss. The only study large enough for its "no" to mean something |
| 4 | Is whole-report assurance associated with fewer later restatements? | No. If anything the opposite: 68% against 44% of company-years restated; not significant |
| 5 | Do government-owned companies score differently on the DQS? | They score lower (delta -0.36), mostly in the first year; not significant with 7 such companies |

## How to read p-values and intervals

> **p-value.** Suppose there were really nothing going on. The p-value is how often chance
> alone would then produce a result at least as far from "nothing" as ours. Small = hard to
> explain by chance. It is **not** the probability that the finding is true, and a large
> p-value is **not** proof that there is nothing.
>
> **raw p and BH p.** Run eight tests and one will look "significant" by luck quite often. The
> BH p (Benjamini-Hochberg) is the p-value after allowing for that. Decisions on this page use
> the BH p against 0.05.
>
> **95% interval.** The range of values the data are compatible with. A wide interval means
> "we do not know", whatever the p-value says. If it contains the "nothing" value (0 for a
> correlation or a change, 1 for an odds ratio, 50% for the share in Study 3), the test does
> not reject.
>
> **Minimum detectable effect.** The smallest true effect this test, with this many
> companies, would find 80 times out of 100. If it is large, a "no" from the test means little:
> the study is **underpowered**. Each study has an effect of practical interest that was fixed
> beforehand; when the minimum detectable effect is above it, the result is marked "likely
> underpowered".
>
> **Unit.** A company that appears in three years is one company, not three pieces of
> evidence. Where it matters, whole companies are shuffled or resampled.

## Study 1. Disclosure quality and carbon intensity

**Question.** Inside a ranking group, do companies with a higher DQS have a different GHG
intensity (Scope 1+2 per Rs crore of turnover)?

**Answer.** No association is found: pooled rank correlation -0.02 in FY2024-25. But the
interval runs from -0.53 to +0.47, and the test could only have found a correlation of 0.68 or
more. This is "we cannot tell", not "there is none".

| Test | n | Statistic | Effect | 95% interval | raw p | BH p | Minimum detectable effect | Decision |
|---|---|---|---|---|---|---|---|---|
| Pooled Spearman correlation, stratified permutation | 24 companies in 4 ranking groups | rho = -0.02 | rho = -0.02 | -0.53 to +0.47 | 0.932 | 0.932 | rho of 0.68 (interest: 0.3) | H0 not rejected; likely underpowered |

Inside the groups (described, not tested one by one): Asset-heavy -0.30 (9 companies), Consumer
-0.21 (5), Energy & utilities +0.30 (5), IT services +0.40 (5). Negative = better disclosure
goes with lower intensity. The signs disagree and no group has more than 9 companies.

Sensitivity (raw p, not part of the decision):

| Variant | n | rho | 95% interval | raw p |
|---|---|---|---|---|
| Groups of 3 or more kept (adds Healthcare) | 27 in 5 groups | +0.03 | -0.45 to +0.48 | 0.90 |
| Unconfirmed and needs-review companies included | 34 in 5 groups | +0.19 | -0.24 to +0.56 | 0.30 |
| FY2023-24, confirmed | 14 in 2 groups | +0.18 | -0.49 to +0.62 | 0.56 |
| FY2025-26, provisional | 39 in 6 groups | +0.17 | -0.22 to +0.51 | 0.35 |

**What it means.** The DQS is not a stand-in for carbon performance: in no variant is a
better score associated with a lower intensity, and in most the sign is the other way round
(weakly). That fits what the score is built to do - say how far the numbers can be trusted, not
whether they are good. What the data cannot do is exclude a moderate association in either
direction.

**Limitations.** 38 companies are in ranking groups where GHG intensity is ranked in
FY2024-25; 14 drop out of the primary test: 3 whose figures a later report does not confirm, 6
that need review, and 5 in two ranking groups then left with fewer than 5 companies (Healthcare
3, Automobiles 2). One year. Financials are not in
it at all. The score is clustered (half of all scores lie between 80 and 90), which leaves
little to rank on. Intensity per rupee differs widely inside a group such as Asset-heavy.

## Study 2. Is GHG intensity falling?

**Question.** Did the GHG intensity of the typical company change from FY2023-24 to FY2024-25?

**Answer.** It fell: the median change is -9.0% (interval -12.2% to -1.7%), and 19 of 25
companies fell. On its own that test clears the 5% bar (raw p = 0.015). After correction for
the eight primary tests it does not (BH p = 0.118), so by the rule fixed beforehand **H0 is not
rejected**. No sector group reaches the bar either.

| Test (Wilcoxon signed-rank) | n | Statistic | Effect: median change | 95% interval | raw p | BH p | Minimum detectable effect | Decision |
|---|---|---|---|---|---|---|---|---|
| All companies | 25 | W = 73 | -9.0% | -12.2% to -1.7% | 0.015 | 0.118 | fall of 10.4% (interest: 5%) | H0 not rejected; likely underpowered |
| Asset-heavy | 11 | W = 22 | -9.0% | -12.2% to +9.5% | 0.365 | 0.487 | fall of 18.9% | H0 not rejected; likely underpowered |
| Asset-light | 8 | W = 8 | -5.5% | -27.8% to +7.0% | 0.195 | 0.313 | fall of 18.1% | H0 not rejected; likely underpowered |
| Financials | 6 | W = 0 | -10.2% | -21.4% to -2.1% | 0.031 | 0.121 | fall of 8.6% | H0 not rejected; likely underpowered |

Sensitivity (raw p, not part of the decision):

| Variant | n | Median change | 95% interval | raw p |
|---|---|---|---|---|
| Every confirmed pair, FY2023-24 to FY2024-25 (no four-year panel, needs-review kept) | 35 | -8.7% | -12.2% to -0.9% | 0.011 |
| - Asset-heavy / Asset-light / Financials | 13 / 13 / 9 | -9.0% / -2.3% / -9.8% | all three include 0 | 0.24 / 0.13 / 0.16 |
| **Long view, FY2022-23 to FY2025-26, unconfirmed values included** | 38 | -29.5% | -43.0% to -0.7% | 0.008 |
| - Asset-heavy / Asset-light / Financials | 15 / 13 / 10 | -3.4% / -41.3% / -44.3% | all three include 0 | 0.23 / 0.13 / 0.38 |

**What it means.** The direction is the same in every variant and every sector group: down.
The size for one confirmed year is about 9% for the typical company. The honest summary is
"probably falling, not established": the evidence would pass as a single test and fails as one
of eight. With five tests in place of eight (the overall test and no sector tests) the BH p
would have been 0.07 - still above 0.05, so the conclusion does not hang on how the family was
drawn. The long view shows a far larger fall, but it rests on the first year (units partly
inferred) and the latest year (not yet confirmed), and its interval nearly touches zero.

**Limitations.** One pair of years, 25 companies. This is the typical company (a median of
company changes), not the group as a whole: the whole Asset-heavy group got slightly more
intensive on the balanced panel (Q1 of [analysis_findings.md](analysis_findings.md)) while its
typical company improved. Turnover is in current rupees, so price rises alone lower intensity
- part of any fall is inflation, not carbon. With 6 companies the test can only reach p < 0.05
when all six move the same way (they did); with 5 it could not reach it at all. "Confirmed"
means the company repeated the figure a year later, not that it is right.

## Study 3. Do restatements flatter the trend?

**Question.** When a company restates a figure materially, does the restatement make its trend
look better more often than a coin toss would?

**Answer.** No. 115 of 241 material restatements with a direction flatter the trend: 47.7%,
interval 41.5% to 54.0%. This study is large enough to have found a 59 / 41 split, so its "no"
carries weight: a strong tilt in the companies' favour is ruled out.

| Test | n | Statistic | Effect: share flattering | 95% interval | raw p | BH p | Minimum detectable effect | Decision |
|---|---|---|---|---|---|---|---|---|
| Exact binomial against 50% | 241 restatements at 41 companies | 115 flattering | 47.7% | 41.5% to 54.0% (Wilson) | 0.520 | 0.594 | 9.3 points from 50% (interest: 10) | H0 not rejected; adequately powered |
| Clustering check: companies resampled | 41 companies | design effect 0.85 | 47.7% | 41.7% to 53.4% | 0.456 | - | - | agrees |

By year of the value (raw p): FY2022-23 46.1% of 115 (0.46), FY2023-24 49.3% of 73 (1.00),
FY2024-25 49.1% of 53 (1.00).

**What it means.** Restatements are corrections that go both ways. There is no sign, in any
year, that companies restate last year's figure to make this year's trend look better. The
interval still allows a mild tilt either way (down to 41.5%, up to 54.0%).

**Limitations.** The share itself was already known from Week 10 (Q9); what is new is the
interval, the clustering check and the power. A restatement of one company is not independent
of its others; here that turned out not to matter (the design effect is below 1, so the
restatements of a company do not all point the same way). "Flatters" is defined per metric
(lower is better, or higher is better); metrics without a direction are left out. A restatement
is a difference between two filings, not a finding of wrongdoing. FY2025-26 cannot be judged
yet.

## Study 4. Assurance of the whole report and later restatement

**Question.** Are company-years whose whole BRSR was assured restated less often in the next
report than those with assurance of the Core only?

**Answer.** No, and the direction is the opposite of what one might expect. At least one
figure was restated materially in 17 of 25 company-years with whole-report assurance (68.0%)
against 30 of 69 with Core-only assurance (43.5%). The odds ratio is 2.7, with an interval from
just under 1 to 8.4. It is not significant (raw p = 0.061, BH p = 0.121), and the study could
only have found a difference of about 31 points or more.

| Test | n | Statistic | Effect: odds ratio | 95% interval | raw p | BH p | Minimum detectable effect | Decision |
|---|---|---|---|---|---|---|---|---|
| Fisher's exact test | 94 company-years at 49 companies (25 whole report, 69 Core only) | +24.5 points in the restated share | 2.73 | 0.96 to 8.37 | 0.061 | 0.121 | 31 points lower or 34 higher (interest: 20) | H0 not rejected; likely underpowered |

Checks (raw p, not part of the decision):

| Check | n | Difference, whole report minus Core only | raw p |
|---|---|---|---|
| Company-cluster permutation, share of company-years restated | 49 companies | +24.5 points | 0.094 |
| Company-cluster permutation, pooled share of compared metrics restated (7.4% against 3.7%) | 49 companies | +3.7 points | 0.064 |
| Company-years with an "assessment" included (odds ratio 2.63, interval 0.93 to 8.00) | 97 company-years | +23.6 points | 0.063 |

**What it means.** There is no evidence that wider assurance is associated with figures that
hold better - the data lean the other way, in all four views. Two readings fit, and this
study cannot choose between them: an assurer who looks at the whole report may find more to
correct, so more gets corrected the year after; or the companies that buy wider assurance
differ from the others in ways not measured here. A restatement is not a mark against a
company: a corrected figure is better than an uncorrected one. So "more restatements" must not
be read as "worse data".

**Limitations.** 25 company-years with whole-report assurance, from two years. Assurance
scope is what the company marks in its own filing; the assurance statement is not read. Only
restatements that appear in the next report are seen. Within a company the two years are not
independent, which is why the cluster check is there; it gives a somewhat larger p. The typical
company-year has few restated metrics (median share 2.9% against 0.0%), so the yes / no outcome
hangs on single figures.

## Study 5. Ownership and disclosure quality

**Question.** Do government-owned companies score differently from private Indian companies
on the DQS?

**Answer.** They score lower: stratified Cliff's delta -0.36, meaning that in a random pair of
one government-owned and one private company of the same year, the private one has the higher
score about 68 times in 100. The interval is -0.71 to +0.01, so it just includes zero, and the
test stops short of the bar (raw p = 0.058, BH p = 0.121). With 7 government-owned companies
the study could only have found a delta of 0.52.

| Test | n | Statistic | Effect: Cliff's delta | 95% interval | raw p | BH p | Minimum detectable effect | Decision |
|---|---|---|---|---|---|---|---|---|
| Stratified Mann-Whitney comparison, permutation by company | 47 companies (7 against 40), 136 yearly scores in 3 years | delta = -0.36 | -0.36 | -0.71 to +0.01 | 0.058 | 0.121 | delta of 0.52, about 8 score points (interest: 0.33) | H0 not rejected; likely underpowered |

By year (Mann-Whitney U, raw p, described only):

| Year | n | Cliff's delta | raw p |
|---|---|---|---|
| FY2022-23 | 44 | -0.64 | 0.009 |
| FY2023-24 | 45 | -0.27 | 0.273 |
| FY2024-25 | 47 | -0.20 | 0.420 |

Sensitivity (raw p): label shuffled only within sector group -0.36 (0.063); provisional
FY2025-26 included -0.29, interval -0.64 to +0.06 (0.127). MNC subsidiaries were not compared:
there are 3.

**What it means.** The gap is real in the first year and has been closing since: -0.64, then
-0.27, then -0.20. Over the three years together it is a medium-sized difference that seven
companies cannot establish. This matches the description in Week 10 (Q8): government-owned
companies were more than eleven points behind in FY2022-23 and level by FY2024-25.

**Limitations.** Seven companies carry one side of the comparison; one of them moving changes
the picture. Government-owned companies sit in a few sectors (four of the seven in energy
and utilities, two in financials); shuffling within sector group gives the same answer, but three sector groups are
coarse. Scores of different years are built from different parts and are only compared within
a year. The yearly p-values are not corrected and the FY2022-23 one was not a planned test.
The score reads the data file, not the printed report.

## Are the methods themselves sound?

Each test was run on made-up data before its result was believed (`python -m
analysis.stats.validate`, and in pytest). "Power" = how often it finds a planted effect in 200
data sets. "False alarms" = how often it reports an effect in 500 data sets that have none; the
target is 5%, the accepted range 2.5% to 8.5% (0% to 8.5% for exact tests on counts, which are
cautious by construction).

| Method | Planted effect | Power | False alarms |
|---|---|---|---|
| Study 1: stratified permutation, 35 companies in 5 groups | correlation 0.6 inside groups | 85.5% | 5.2% |
| Study 2: Wilcoxon signed-rank, 20 companies | median change -11% | 87.0% | 3.0% |
| Study 3: exact binomial, about 240 restatements | 62% flattering | 93.5% | 5.6% |
| Study 3: company-cluster bootstrap, clustered restatements | 75% flattering | 85.5% | 4.2% |
| Study 4: Fisher's exact test, 96 company-years | odds ratio about 0.14 | 97.0% | 2.4% |
| Study 4: company-cluster permutation | odds ratio about 0.14 | 79.5% | 3.0% |
| Study 5: permutation by company, 7 against 41 | 8 score points | 94.0% | 6.6% |

One more check shows why Study 3 has a clustering check at all: on made-up restatements that
cluster strongly by company and have no tilt, the plain binomial test raises a false alarm in
41.6% of data sets. The cluster bootstrap stays at 4.2%. In the real data the two agree.

All five studies also run on synthetic gold tables in pytest, and on the one-company warehouse
that CI builds, where each must answer "not enough data" and not a number.

## Against pre-registration

What differs from [stats_hypotheses.md](stats_hypotheses.md), and why. No test, filter, year or
decision rule was changed after the results were seen.

| # | Planned | Done | Why | Changes a conclusion? |
|---|---|---|---|---|
| 1 | "Seed 20261013 for every study" | The seed is combined with a study number and a step number (permutation, bootstrap, power simulation) | So that skipping the slow power simulation does not change the p-values of the same run | No |
| 2 | Study 3: minimum detectable effect "at the effective number" of restatements | The design effect came out below 1 (0.85); the effective number is capped at the actual 241 | A design effect below 1 would have made the study look larger than it is | No (9.3 points either way) |
| 3 | Study 2: power simulation with the Wilcoxon test of scipy | Same test; for up to 13 companies the exact p-value is counted directly over all sign patterns | Speed (8.5 minutes down to 5 seconds). A test checks that the p-values are identical to scipy's | No |
| 4 | Study 5: "41 private Indian" companies | 40 in the primary test | One has no score with three components in the final years; the filter is as planned | No |
| 5 | Method checks: planted effect and no effect per test | Added: the plain binomial and Fisher tests on clustered data with no effect | To show what the clustering checks protect against | No (not a test on real data) |
| 6 | - | "With five tests the BH p of Study 2 would have been 0.07" is quoted | An after-the-fact remark on how much the choice of family matters; labelled as such, not used for the decision | No |

Not deviations, but worth knowing: Study 1 lost two ranking groups to the 5-company rule as
planned (Healthcare, Automobiles); the MNC comparison of Study 5 did not run as expected; the
yearly figures of Studies 3 and 5 and all sensitivity rows are raw, uncorrected and were never
part of a decision.

## What to take away

- **One solid "no"**: restatements do not flatter trends (Study 3).
- **One "probably"**: carbon intensity of the typical company fell by about 9% in the one
  year that can be confirmed (Study 2). Not established by the rule set beforehand.
- **Two leanings worth a second look with more data**: government-owned companies disclose
  less well, but the gap is closing (Study 5); whole-report assurance is associated with more,
  not fewer, later corrections (Study 4).
- **One "cannot tell"**: disclosure quality and carbon intensity (Study 1).
- With about 50 companies and two or three usable years, only large effects can be shown.
  Each further year of filings adds confirmed pairs to Studies 1, 2 and 4.
