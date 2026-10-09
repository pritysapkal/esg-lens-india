# Parser validation (Module 2)

How we know `ingestion/parse_xbrl.py` reads BRSR XBRL filings correctly. Real filings are
never committed (NSE terms of use, [ADR 0002](adr/0002-manual-intake-nse-terms.md)), so this page
shows counts and match rates only. Filed values stay in the git-ignored `data/` folder.

Last run: 2026-10-09, parser version 1.0.0, Arelle (arelle-release) 2.46.0.

## 1. Reference filing: HDFC Bank FY2025-26

The expected numbers were counted independently in week 1 (`ingestion.instance.count_instance`,
see `tests/test_realdata.py`).

| Check | Expected | Parser |
|---|---|---|
| Facts (`facts` + `text_facts`) | 2,182 | 2,182 ✅ |
| Distinct concepts | 618 | 618 ✅ |
| Contexts | 658 | 658 ✅ |
| Units | 11 | 11 ✅ |
| Main period | 2025-04-01 .. 2026-03-31, 12 months | same ✅ (context `DCYMain`) |
| `TotalScope1Emissions`, `TotalScope2Emissions`, `PercentageOfGrossWagesPaidToFemaleToTotalWagesPaid` (current year, no dimensions) | values from the filing | `raw_value` identical ✅ |

The non-standard period check: NESTLEIND 2023-2024 runs **2023-01-01 .. 2024-03-31 (456 days,
15 months)**, because Nestlé India moved its financial year from calendar year to April-March.
It is the only non-standard period among the 196 filings.

Both checks run as `@pytest.mark.realdata` tests and skip when the files are absent.

## 2. Arelle cross-check

`scripts/arelle_crosscheck.py` loads five filings with [Arelle](https://arelle.org) and compares
them with the parser output. Together they cover 4 of the 5 taxonomy versions; 2023-06-30 is not
in the set.

**Offline setup.** The schemaRef in each filing is a bare file name
(`in-capmkt-ent-<version>.xsd`), so Arelle resolves it next to the instance. The script copies
the instance and its local taxonomy version (`BRSR/` + `core/` from `data/raw/taxonomy/`) into a
temporary directory, which is deleted afterwards. Arelle runs with `workOffline = True` and
validation off, and the core XBRL schemas come from Arelle's bundled cache. All five filings
loaded offline with **0 warnings/errors and 0 undefined concepts**.

**What is compared:**

- the fact, context and unit counts;
- 20 numeric, non-nil facts per filing, chosen at random (fixed seed). Each one is matched to
  Arelle by concept, context and unit, and must have the same raw string and the same decimal
  value;
- every fact, as a multiset of (namespace, concept, context, unit, nil flag, value);
- every context, by period type, start/end/instant date and `dimension_key` (explicit and
  typed members).

<!-- results:start -->
| Filing | Taxonomy | Facts (parser / Arelle) | Contexts | Units | 20 sampled numeric values equal | All facts equal | All contexts equal |
|---|---|---|---|---|---|---|---|
| HDFCBANK FY26 | 2026-02-28 | 2,182 / 2,182 ✅ | 658 / 658 ✅ | 11 / 11 ✅ | 20/20 | 2,182/2,182 | 658/658 |
| RELIANCE FY25 | 2025-05-31 | 3,604 / 3,604 ✅ | 937 / 937 ✅ | 10 / 10 ✅ | 20/20 | 3,604/3,604 | 937/937 |
| TCS FY24 | 2024-04-30 | 2,198 / 2,198 ✅ | 622 / 622 ✅ | 10 / 10 ✅ | 20/20 | 2,198/2,198 | 622/622 |
| SBIN FY23 | 2021-09-30 | 1,943 / 1,943 ✅ | 669 / 669 ✅ | 2 / 2 ✅ | 20/20 | 1,943/1,943 | 669/669 |
| NESTLEIND 2023-2024 | 2024-04-30 | 2,004 / 2,004 ✅ | 560 / 560 ✅ | 11 / 11 ✅ | 20/20 | 2,004/2,004 | 560/560 |
<!-- results:end -->

The sampled values (concept, context, both raw strings) are written to
`data/processed/arelle_crosscheck_values.csv`, which is git-ignored. The script rewrites the table
above on each run.

## 3. Full run (196 filings)

`python -m ingestion.parse_xbrl` parsed all 196 received filings in about 31 s with 0
failures:

| | Count |
|---|---|
| Facts (all) | 419,204 |
| of which numeric (have a unit) | 241,635 |
| of which `text_facts` (TextBlock or > 1,000 chars) | 19,705 |
| Contexts | 121,891 |
| Units | 1,714 |

Facts per taxonomy version: 2021-09-30: 57,850 · 2023-06-30: 29,754 · 2024-04-30: 106,503 ·
2025-05-31: 109,303 · 2026-02-28: 115,794.

These totals match a separate lxml scan of the raw files (context, unit and fact counts per
namespace). All 419,204 `fact_id`s are unique.

## Notes on parser behaviour

- **`raw_value`** is the element text exactly as filed, after XML entity decoding. It is never
  cast or stripped, so `0.0000000888` and `11111.10` keep their form. Nil facts have
  `raw_value = NULL` and `is_nil = true`.
- **`fact_id`**: none of the 196 filings sets an `id` on facts, so `fact_id` is a sha256 (first
  32 hex characters) of filing_id, sequence, concept, context and unit. It is stable on re-runs.
- **Text split**: a fact goes to `text_facts` if its concept ends with `TextBlock` or its value is
  longer than 1,000 characters. Of the 19,705 text facts, 428 qualify on length only.
- **Main period**: the duration context with no dimensions and the latest end date. Ties go to
  the context with the most facts, then the earliest start. `period_months =
  round(inclusive_days / 30.4375)`.
- **Encodings**: lxml honours the BOM and the XML declaration. Tests cover UTF-8 with BOM and
  UTF-16. All 196 real files are UTF-8 without a BOM.
