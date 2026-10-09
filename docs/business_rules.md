# Business rules (intermediate layer)

Rules applied in `dbt/models/intermediate/` when turning filed BRSR values into comparable
metrics. Each rule was checked against the data before it was applied. Every changed value keeps
its original (`raw_value`, `value_num`) and says why (`normalisation_flag`, `correction_reason`).
All flagged values are collected in `int_normalisation_exceptions`.

Data: 196 filings (FY2022-23 to FY2025-26), parsed on 2026-10-09. The numbers below come from
that run and change when filings are added. Re-check them with the queries in each section.

## 1. Turnover scale (`int_turnover_corrected`)

**Problem.** `Turnover` must be filed in rupees, but some filers enter crore (14,700.05 = Rs 14,700
crore), million or lakh. The value is then 10^5-10^7 too small, and so is every intensity built
on it.

**Rule.** A turnover below 10^9 INR (Rs 100 crore) is not plausible for a NIFTY 50 company. For
each such filing, try the scales crore (x10^7), million (x10^6) and lakh (x10^5), and keep the one
that lands closest (log distance) to the median of the company's other plausible years
(>= 10^9). Without such years, crore is the default. The filer's own arithmetic is supporting
evidence: `evidence_ratio = filed Scope 1+2 / turnover_raw / filed intensity per rupee` is about
equal to the scale when the filer computed the intensity in rupees.

**Why not always x10^7?** The comparison with other years rejects crore for 5 filings:

- DRREDDY FY2022-23 to FY2024-25 (169,625 / 194,838 / 231,154): million. x10^6 gives 0.83-1.13x
  the FY2025-26 value; x10^7 would give 8-11x.
- SUNPHARMA FY2022-23 (203,946.3): million, 0.98x the other years.
- BSE FY2025-26 (446,951): lakh, 4.4x the median of the earlier years (BSE grew fast). Crore would
  be 440x. The filer's intensity arithmetic also implies lakh (evidence_ratio 10^5.0).
  Confidence medium.

**Corrected: 24 filings in 14 companies** (19 crore, 4 million, 1 lakh). 22 have high
confidence and 2 medium (EICHERMOT FY2025-26: 1.6x the only other plausible year; BSE
FY2025-26).

| Company | Fiscal years corrected | Scale |
|---|---|---|
| ADANIENT | FY2022-23 | crore |
| CIPLA | FY2022-23 | crore |
| COALINDIA | FY2022-23, FY2023-24, FY2024-25 | crore |
| DRREDDY | FY2022-23, FY2023-24, FY2024-25 | million |
| EICHERMOT | FY2023-24, FY2024-25, FY2025-26 | crore |
| HINDUNILVR | FY2024-25, FY2025-26 | crore |
| INFY | FY2025-26 | crore |
| JIOFIN | FY2024-25 | crore |
| POWERGRID | FY2023-24, FY2025-26 | crore |
| SUNPHARMA | FY2022-23 | million |
| TATACONSUM | FY2022-23, FY2023-24, FY2025-26 | crore |
| TITAN | FY2022-23 | crore |
| ULTRACEMCO | FY2025-26 | crore |
| BSE | FY2025-26 | lakh |

**Not corrected, but flagged for review.** These look plausible (>= 10^9) but are far from the
company's other years. The < 10^9 rule cannot see them:

| Filing | Filed turnover | x other years | Confidence | Likely cause |
|---|---|---|---|---|
| TCS FY2022-23 | 2.25e9 | 0.001 | low | filed in thousands (x1000) |
| BEL FY2023-24 | 1.98e9 | 0.009 | low | ~x100 off |
| BAJAJFINSV FY2023-24 | 1.73e10 | 0.02 | low | standalone (holding company) vs consolidated |
| BAJAJFINSV FY2022-23 / FY2024-25 / FY2025-26 | | 5.5 / 8.9 / 0.18 | medium | boundary changes between years |
| JSWSTEEL FY2022-23 | 1.30e11 | 0.10 | medium | ~x10 off |
| BSE FY2022-23 / FY2024-25 | | 0.33 / 3.2 | medium | fast growth |

Turnover is filed only for the current year (there is no PY comparative to cross-check).

## 2. MtCO2e (`unit_normalisation`, `int_mtco2e_check`)

**Rule.** The unit label `MtCO2e` (89 filings) is read as **metric tonnes** (x1), not megatonnes.

**Evidence.** When a company switches between `MtCO2e` and `tCO2e` from one filing to the next,
the comparative (PY) value in the new filing equals the previous filing's current value:

- MtCO2e filing followed by a tCO2e filing: 25 of 28 Scope 1/2 pairs match within 5 %.
- tCO2e filing followed by an MtCO2e filing: 17 of 17 match.

**Check (reported, not corrected).** For each MtCO2e filing, Scope 1+2 intensity (tCO2e per rupee
crore of corrected turnover) is compared with the company's other years and with its industry
peers (at least 3 other companies). A value 10^4 or more below a reference is flagged
`likely_megatonnes`:

| Filing | Filed Scope 1 | Intensity vs reference | Finding |
|---|---|---|---|
| NTPC FY2023-24 | 352.47 MtCO2e | 10^-6 x its other years | megatonnes (the FY2022-23 filing says "Million metric tonnes"; FY2024-25 files 3.27e8 tCO2e) |
| TATASTEEL FY2023-24 | 56 MtCO2e | 10^-6 x Metals & Mining peers | megatonnes (FY2022-23 says "Million tonnes", 75.75) |
| TATASTEEL FY2024-25 | 61 MtCO2e | 10^-6 x peers | megatonnes |
| TATASTEEL FY2025-26 | 64 MtCO2e | 10^-6 x peers | megatonnes |

One more filing is flagged as implausible (BEL FY2023-24: 150x its other years), but the cause
there is the turnover (section 1), not the unit. **Decision needed:** these 4 filings still use
x1 in `int_metric_values`. Correcting them (x10^6) needs an explicit override, which is not
built yet.

## 3. Old-taxonomy units (`int_implied_units`)

**Problem.** In the 2021-09-30 and 2023-06-30 taxonomies (47 filings, mostly FY2022-23),
emissions, energy, water and waste are filed with unit `pure`. For emissions, the real unit is
typed as free text in a companion fact (`UnitOfTotalScope1Emissions`, ...), with values such as
"Metric tonnes of CO2 equivalent", "Million tonnes of CO2 equivalent", "Kilo tonnes" and "grams
CO2 equivalent". Energy, water and waste have no unit at all.

**Rule, in order of preference:**

1. **Bridge from the next filing.** The company's next filing repeats the same year as its PY
   value, with a real unit. If that value matches this filing's CY value within 5 %, its unit is
   used (298 filing-metric pairs). This catches companies that file energy in MJ or TJ: 6 + 6
   pairs that a GJ default would have got wrong by 1000x.
2. **Text unit** via `seeds/text_unit_normalisation.csv`, only if it converts to the metric's unit
   (49 pairs). Million tCO2e: GRASIM, HINDALCO, LT, NTPC, TATASTEEL; ktCO2e: ITC; grams: SBILIFE.
   In every case the converted value matches the next filing's comparative (e.g. GRASIM 4.72
   million = 4,724,656 t; SBILIFE 86,730,000 g = 86.73 t).
3. **Format default** (tCO2e, GJ, kl, t, per rupee), flagged `unit_format_default` (253 pairs,
   mostly zero or unmatched values).

**Conflict.** When the bridge says `MtCO2e` (x1) but the text says "million" (x10^6), the text
wins (NTPC FY2022-23 Scope 1 and 2: 335.72 = 3.36e8 t). This is the same megatonne use of "Mt" as
in section 2.

**Old Scope 3** is filed as text (`stringItemType`). Numbers are parsed from it after removing
thousands separators (Indian grouping "20,23,072" = 2,023,072) and flagged `numeric_from_text`
(75 values).

**Renamed concepts** (checked against labels and values):

- `TotalEnergyConsumption` (2021/2023) -> `TotalEnergyConsumedFromRenewableAndNonRenewableSources`.
  It equals renewable + non-renewable within 1 % in 71 of 94 contexts.
- `TotalScope1AndScope2EmissionsPerRupeeOfTurnover` (2021/2023) ->
  `TotalScope1AndScope2EmissionsIntensityPerRupeeOfTurnover`. The labels differ only by
  "intensity".
- Not treated as a rename: `WhetherTheCompanyHasUndertakenReasonableAssuranceOfTheBRSRCore`
  (2024-04-30, true/false) vs `WhetherTheCompanyHasUndertakenAssessmentOrAssuranceOfTheBRSRCore`
  (2025+, "Yes assurance"/"Yes assessment"). The older question asks only about *reasonable*
  assurance, so it is not mapped.

## 4. Percentages (`unit_normalisation`: pure -> pct)

**Rule.** Percent concepts are filed as decimals (0.2036 = 20.36 %), so `value_pct = value x 100`.
A value above 1 is taken as already in percent: it is not multiplied again and is flagged
`pct_given_as_0_100`.

**Evidence.** Of 7,781 percent values, 7,778 are between 0 and 1. The 3 above 1:

| Filing | Metric | Filed | Read as |
|---|---|---|---|
| COALINDIA FY2024-25 | msme_sourcing_pct | 59.62 | 59.62 % |
| TECHM FY2023-24 (urban) | job_creation_small_towns_pct | 8.2399 | 8.24 % |
| POWERGRID FY2023-24 (PY2, permanent employees) | attrition_rate_pct | 4.88 | 4.88 % (ambiguous: could be 488 %) |

A small percentage typed as a whole number below 1 (e.g. "0.5" meaning 0.5 %) cannot be told
apart from a decimal and is read as 50 %. The values that equal exactly 1.0 (100 %) are kept.

## 5. ISO durations (`days_payable`)

`NumberOfDaysOfAccountsPayable` is an XBRL duration, e.g. `P59D`. It is parsed to a number of
days. All 298 values have the form `P<n>D` (0 unparsed). Financial companies should be excluded
when comparing (shortlist note).

## 6. Intensity units

Filed intensities are converted to "per rupee crore" (x10^7, with the energy unit conversion for
MJ/TJ). They are `check_only` metrics: the shortlist found many filed intensities off by
10^6-10^7, so the headline intensities will be recomputed from totals and corrected turnover.

## 7. NA, zero and missing

These are kept apart and never merged:

| State | How it shows | Count in `int_metric_values` |
|---|---|---|
| Not applicable / not available (NA, N/A, "-", ...) | `is_na_text = true`, `value_std` null | 2 (the catalogue is mostly numeric) |
| Zero | `is_zero = true`, `value_std = 0` | 6,195 of 21,730 |
| Nil (XBRL nil) | `is_nil = true` | 0 (no filing uses nil) |
| Missing (not filed) | **no row** | - |

A zero is a reported value. For example, zero water withdrawal at an NBFC means "not material",
not "best in class" (shortlist note), so the marts must treat it in context.

## 8. Numeric precision

`value_std` is rounded to 15 significant digits after unit conversion, which removes float noise
(8.88e-8 x 10^7 = 0.888, not 0.8880000000000001). Filed values have at most 15 significant
digits (checked in week 4), so no information is lost.

## 9. Period roles (`int_period_role`)

Roles are anchored on each filing's own main period, not on a calendar: CY ends on the filing's
period end, PY ends the day before it starts, and PY2 ends the day before PY starts.
`value_fiscal_year_label` is the April-March financial year in which the value's period ends.
This keeps NESTLEIND right:

| Filing | CY | PY | PY2 |
|---|---|---|---|
| FY2023-24 (15 months) | 2023-01-01..2024-03-31 (FY2023-24) | calendar 2022 (FY2022-23) | - |
| FY2024-25 | 2024-04-01..2025-03-31 | the 15-month period (FY2023-24) | calendar 2022 (FY2022-23) |

Of 399,499 facts: CY 309,463, PY 78,577, INSTANT_CY 5,623, INSTANT_PY 4,276, PY2 1,544 and
OTHER 16. The 16 OTHER values are attrition PY2 values with mistyped end dates (JIOFIN FY2024-25:
2023-04-01; INDIGO FY2024-25: 2023-03-01). They are kept but not treated as a comparative year.
