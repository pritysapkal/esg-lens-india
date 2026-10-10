# Restatement tracker - method

`fct_restatement` compares, for each company, metric and breakdown, the number a company filed for a
year with the comparative number for the same year in the **next** year's report. `rpt_restatement_summary`
aggregates it. **A restatement is a difference between two filings. It is not a finding of
wrongdoing**: companies restate for sound reasons (corrected errors, new methods, mergers).

## Definitions

| Term | Meaning |
|---|---|
| Original value | The current-year (CY) value of year Y from the company's filing for Y (latest revision). |
| Restated value | The prior-year (PY) value for year Y in the filing for Y+1 (latest revision). |
| Pair | One original and one restated value of the same company, metric, breakdown (`dimension_key`) and year. |
| Compared pair | A pair not excluded as circular (see below). Only compared pairs enter any statistic. |

Pairs: FY2022-23 -> FY2023-24, FY2023-24 -> FY2024-25, FY2024-25 -> FY2025-26. Metrics: headline,
input and secondary numeric catalogue metrics, both values after unit normalisation and approved
overrides (`value_std`). Breakdown member names are identical in all five taxonomy versions
(checked), so no `dimension_member_map` seed was needed.

## Change measures

- `abs_change` = restated - original
- `pct_change` = (restated - original) / |original| (empty when the original is 0)
- `pp_change` = restated - original, only for percent metrics (`unit_type = 'pct'`)

## Classification (exactly one, evaluated in this order)

1. **`unit_inferred_from_restating_filing`** - the original's unit was inferred from the next filing
   (`unit_resolution_method = bridged-from-next-filing`). Comparing it with that same filing is
   circular, so these pairs are **excluded from all statistics** (`is_compared = false`).
2. **`unit_inconsistency`** - restated / original is within 5% of 10^k for k in +-2, +-3, +-5, +-6,
   +-7: almost certainly a unit or scale difference, not a restatement.
3. **`from_zero`** / **`to_zero`** - original 0 and restated not, or the reverse.
4. **`no_change`** - |pct_change| <= 1% (rounding tolerance), or no change at all.
5. **`material`** - |pct_change| > 5% **and**, for percent metrics, |pp_change| > 1 point; for count
   metrics, |abs_change| >= 2; for other metrics no further condition.
6. **`minor`** - everything else (a change that is more than rounding but below the thresholds).

## Explained or unexplained (`explained_by`)

In this order:

1. `merger/demerger` - `dim_company_year` of Y+1 has `has_comparability_break` with a merger or
   demerger (seed `corporate_events`);
2. `boundary change` - the break reason is a change of reporting boundary;
3. `restatement note in filing` - a long text fact of the Y+1 filing matches a restatement phrase
   (word starts: restat, re-stat, regroup, reclassif; or "revised" next to figures / data / numbers /
   values). A snippet of at most 300 characters is stored in `stated_reason`, links removed.
4. otherwise empty = **unexplained**.

The text test is deliberately narrow: "revised" alone matches policy texts in most filings, and
"restat" matches "afforestation". It is still a filing-level match: a note somewhere in the report,
not proof that it refers to that metric. Read `stated_reason` before relying on it.

## Flattering (`flatters_trend`) and red flags

For material pairs, using `dim_metric.direction`:

- lower is better: flattering if restated > original (the Y -> Y+1 change then looks like an
  improvement);
- higher is better: flattering if restated < original.

Metrics with no direction (context, n/a) have no flattering flag. **`red_flag`** = material AND
unexplained AND flattering. A red flag is a prompt to read the two filings, not a conclusion.

## Thresholds in one place

| Threshold | Value |
|---|---|
| Rounding tolerance (no change) | 1% |
| Material change | > 5% (and > 1 pp for percent metrics, >= 2 for counts) |
| Unit inconsistency | ratio within 5% of 10^k, k in {+-2, +-3, +-5, +-6, +-7} |
| Stated reason | <= 300 characters, no links |

## Headline numbers (build of 2026-10-10)

- 4,399 pairs, 245 circular (excluded), **4,154 compared**.
- no change 86.7%, minor 3.5%, **material 7.5% (310)**, from zero 1.9%, to zero 0.3%, unit
  inconsistency 0.1%.
- Of the 310 material restatements: 172 (55.5%) unexplained; 131 (42.3%) flatter the trend; **78 red
  flags**.
- **43 of 50 companies (86%)** with comparable pairs have at least one material restatement. This
  sits above the KPMG 2026 survey figure (45 of 94 NIFTY 100 companies, about 48%) because our
  rule counts every metric and breakdown and keeps FY2022-23 values filed under older taxonomies;
  see the limitations below.

## Limitations

- **Only three comparison pairs** (FY23 -> FY24, FY24 -> FY25, FY25 -> FY26). FY2021-22 originals
  are out of scope; the second comparative (PY2) is kept in `fct_esg_value` but not compared.
- **FY2022-23 originals are noisy.** 140 of the 310 material restatements (and 48 of the 78 red
  flags) are in the first pair, and the largest are scale errors in the original (for example Coal
  India waste, 3,880 t against 4.3 billion t restated; ratios that are not near a power of ten
  escape the unit rule). Units for old-taxonomy filings were inferred (`normalisation_flag`).
  Treat FY2022-23 material restatements as a data-quality list first.
- **No comparatives are filed** for turnover, headcount and women on the board, so those metrics
  have no pairs.
- **Explanations are weak evidence.** The text match is per filing, and boundary / event flags
  explain at the company-year level, not the metric.
- **Dimension coverage:** pairs need the same breakdown member on both sides; values missing on
  one side (a new breakdown, a filed NA) are not compared.
- **Restatement is not wrongdoing.** A flattering, unexplained change can still be a correction.
