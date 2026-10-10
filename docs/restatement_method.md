# Restatement tracker - method

`fct_restatement` compares, for each company, metric and breakdown, the number a company filed for a
year with the comparative number for the same year in the **next** year's report. `rpt_restatement_summary`
aggregates it. **A restatement is a difference between two filings. It is not a finding of
wrongdoing**: companies restate for sound reasons (corrected errors, new methods, mergers).

## Definitions

| Term | Meaning |
|---|---|
| Original value | The current-year (CY) value of year Y from the company's filing for Y (latest revision), as filed (`value_std`). |
| Restated value | The prior-year (PY) value for year Y in the filing for Y+1 (latest revision). |
| Pair | One original and one restated value of the same company, metric, breakdown (`dimension_key`) and year. |
| Compared pair | A pair that is neither circular nor a suspected scale error (`is_compared`). Only compared pairs enter any statistic. |

Pairs: FY2022-23 -> FY2023-24, FY2023-24 -> FY2024-25, FY2024-25 -> FY2025-26. Metrics: headline,
input and secondary numeric catalogue metrics, both values after unit normalisation and approved
overrides. Breakdown member names are identical in all five taxonomy versions (checked), so no
`dimension_member_map` seed was needed.

## Change measures

- `abs_change` = restated - original
- `pct_change` = (restated - original) / |original| (empty when the original is 0)
- `pp_change` = restated - original, only for percent metrics (`unit_type = 'pct'`)
- `ratio` = restated / original (both positive)

## Classification (exactly one, evaluated in this order)

1. **`unit_inferred_from_restating_filing`** - the original's unit was inferred from the next filing
   (`unit_resolution_method = bridged-from-next-filing`). Comparing it with that same filing is
   circular. **Excluded from all statistics.**
2. **`suspected_scale_error`** - `ratio` above 100 or below 0.01, whatever the exact magnitude;
   for **percent metrics** (`unit_type = 'pct'`) the threshold is tighter: ratio >= 10 or <= 0.1.
   A number that changes more than a hundredfold between two reports is a unit or scale mistake
   in one of them (tonnes typed as million tonnes, GJ as TJ), not a restatement. A percentage
   cannot plausibly move tenfold; the usual slip is a fraction filed where a percent is meant
   (attrition 0.5 in one report, 8.8 in the next). **Excluded from all statistics**, listed in
   `int_scale_error_suspects` for the Disclosure Quality Score.
3. **`unit_inconsistency`** - ratio within 5% of 10^k for k in +-2, +-3, +-5, +-6, +-7 (after rule 2
   only the +-2 band, ratio 95-100 or 0.0100-0.0105, can still apply).
4. **`from_zero`** / **`to_zero`** - original 0 and restated not, or the reverse.
5. **`no_change`** - |pct_change| <= 1% (rounding tolerance), or no change at all.
6. **`material`** - |pct_change| > 5% **and**, for percent metrics, |pp_change| > 1 point; for count
   metrics, |abs_change| >= 2; for other metrics no further condition.
7. **`minor`** - everything else.

## Best available value (scale errors)

`value_std` in `fct_esg_value` always keeps what was filed. Gold KPIs use **`best_value_std`**:

- if the official current value of year Y is a suspected scale error against the comparative for Y
  in the Y+1 report, `best_value_std` = that later comparative and `best_value_source` =
  `replaced_by_later_comparative`;
- otherwise `best_value_std` = `value_std` and `best_value_source` = `as_filed`.

The later report is preferred because the company has had a year to correct it and it is filed in
a newer taxonomy with explicit units. `fct_company_year`, `fct_peer_benchmark` and
`fct_company_kpi_percentile` read `best_value_std`; `n_values_replaced` and the flag
`scale_error_values_replaced` say when a company-year is affected. Filed intensities are never
replaced (their denominators differ by design, see `ghg_intensity_filed_basis`). The latest year
(FY2025-26) has no later report, so its scale errors cannot be caught this way.

Current data: 39 values replaced in 19 company-years: 21 quantities (mostly total and renewable
energy, FY2022-23) and 18 percentages (13 of them attrition rates). Example: AXISBANK FY2022-23 total energy 1,005 GJ as
filed, 1,994,830 GJ in the next report; renewable share goes from 1,143% to 0.58%.

## Explained or unexplained (`explained_by`)

In this order:

1. `merger/demerger` - `dim_company_year` of Y+1 has `has_comparability_break` with a merger or
   demerger (seed `corporate_events`);
2. `boundary change` - the break reason is a change of reporting boundary;
3. `possible note (weak)` - a long text fact of the Y+1 filing contains a restatement word. Whole
   words only: restated / restatement(s), regrouped / regrouping, reclassified / reclassification,
   or "revised" within 40 characters of number / figure / data. A snippet of at most 300 characters
   is stored in `stated_reason`, links removed.
4. otherwise empty = **unexplained**.

The note is **weak** evidence: it is a match somewhere in the report, not proof that it refers to
that metric. Read `stated_reason` before relying on it.

## Flattering (`flatters_trend`) and red flags

For material pairs, using `dim_metric.direction`:

- lower is better: flattering if restated > original (the Y -> Y+1 change then looks like an
  improvement);
- higher is better: flattering if restated < original.

Metrics with no direction (context, n/a) have no flattering flag.

- **`red_flag`** = material AND flattering AND no explanation of any kind.
- **`red_flag_strict`** = material AND flattering AND not explained by a merger / demerger or a
  boundary change. A weak note does **not** count as an explanation here, so it is the larger set.

A red flag is a prompt to read the two filings, not a conclusion.

## Thresholds in one place

| Threshold | Value |
|---|---|
| Suspected scale error | ratio > 100 or < 0.01; percent metrics: ratio >= 10 or <= 0.1 |
| Rounding tolerance (no change) | 1% |
| Material change | > 5% (and > 1 pp for percent metrics, >= 2 for counts) |
| Unit inconsistency | ratio within 5% of 10^k, k in {+-2, +-3, +-5, +-6, +-7} |
| Stated reason | <= 300 characters, no links |

## Headline numbers (build of 2026-10-10)

- 4,399 pairs; 245 circular and 39 suspected scale errors excluded; **4,115 compared**.
- no change 87.5%, minor 3.6%, **material 6.7% (274)**, from zero 1.9%, to zero 0.3%, unit
  inconsistency 2 pairs.
- Of the 274 material restatements: 128 unexplained, 93 with only a weak note, 53 explained by a
  merger / demerger or boundary change.
- **61 red flags, 98 strict red flags.**
- All metrics and breakdowns: 42 of 50 companies (84%) have at least one material restatement.

### Comparable with KPMG (`level = 'kpmg_comparable'`)

KPMG 2026 reports that **45 of 94 NIFTY 100 companies (about 48%)** revised prior-year BRSR figures.
Our closest definition: headline totals only (Scope 1, Scope 2, total energy, water withdrawal,
waste generated; company-wide values), circular pairs and suspected scale errors excluded, a
company counts if it has at least one material restatement.

| Pairs | Compared pairs | Companies with comparable pairs | With >= 1 material restatement | Share |
|---|---:|---:|---:|---:|
| FY2023-24 -> FY2024-25 only | 239 | 48 | 8 | 16.7% |
| All three pairs | 546 | 50 | 24 | 48.0% |

**Definitions still differ**: KPMG's universe is the NIFTY 100 (ours is the NIFTY 50 plus Wipro),
their list of indicators and their threshold for "revised" are not published in a form we can
replicate, and we require a change above 5%. The match of the all-pairs figure with 48% is not
evidence that the two measures are the same.

## Limitations

- **Only three comparison pairs** (FY23 -> FY24, FY24 -> FY25, FY25 -> FY26). FY2021-22 originals
  are out of scope; the second comparative (PY2) is kept in `fct_esg_value` but not compared.
- **FY2022-23 originals are noisy.** Units for old-taxonomy filings were inferred, so the first
  pair holds most circular pairs and most scale errors, and still a large share of the material
  restatements. Treat FY2022-23 material restatements as a data-quality list first.
- **The scale-error rule is blunt.** A real hundredfold change (a start-up year), or a real tenfold
  change in a percentage, would be excluded and its value replaced; a tenfold unit slip in a
  quantity (for example ITC waste recovered 71,800 -> 718,000 t) is still read as a material
  restatement.
- **No comparatives are filed** for turnover, headcount and women on the board, so those metrics
  have no pairs.
- **Explanations are weak evidence.** The text match is per filing, and boundary / event flags
  explain at the company-year level, not the metric.
- **Dimension coverage:** pairs need the same breakdown member on both sides; values missing on
  one side are not compared.
- **Restatement is not wrongdoing.** A flattering, unexplained change can still be a correction.
