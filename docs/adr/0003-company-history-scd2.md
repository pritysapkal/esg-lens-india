# ADR 0003 - Company name history is a derived SCD type 2, not a dbt snapshot

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Companies change name and NSE symbol (Zomato became Eternal; Tata Motors became Tata Motors
Passenger Vehicles, symbol TMPV). Reports must show the right name for each financial year, and
the company key must stay the same. The key is the ISIN.

dbt offers `snapshots` for slowly changing dimensions. A snapshot works by comparing a source
table with its own previous state on every run and stamping `dbt_valid_from` / `dbt_valid_to`
with the **time of the run**.

## Decision

`dim_company_history` is built as a normal mart model from the filing history
(`int_company_names`), not as a dbt snapshot.

- One row per run of consecutive financial years in which a company filed under the same
  cleaned name and symbol.
- Columns: `isin`, `company_name`, `symbol`, `valid_from_fy`, `valid_to_fy`, `is_current`
  (+ `n_years`, `version_number`).
- `valid_from_fy` is the first year filed under the name; `valid_to_fy` is the last year seen
  with it and is empty for the current row.

## Why not a snapshot

- **The data is yearly and the dates are business dates.** A snapshot records *when dbt ran*, so
  a name change in FY2024-25 would be stamped with the day we first loaded that file. The right
  validity is the financial year in the filing, which is already in the data.
- **A snapshot cannot be rebuilt.** Its history exists only in the warehouse. Deleting the
  DuckDB file (we rebuild from files often) loses it. A derived table is rebuilt from the
  filings in seconds and gives the same result every time.
- **Late-loaded history.** Filings for earlier years can arrive after later ones (manual
  intake). A snapshot would record the old name as the "new" version when it arrives; the
  derived table orders by financial year and is correct whatever the load order.
- **Testable.** "No overlapping validity" and "exactly one current row" are plain SQL tests on
  deterministic output (`assert_company_history_*`).

Snapshots stay the right tool for the restatement tracker (values that change between loads
of the *same* year); that module is separate and still planned.

## Consequences

- History only goes back as far as the filings (FY2022-23). A rename before that is not visible.
  At the time of writing the filings contain **no** name change: Eternal appears from FY2024-25
  as "Eternal Limited" (no Zomato filing is in the set) and TMPV only has its FY2025-26 filing
  under its new name. The table is ready for such changes when older filings are added.
- A name change is detected only between two consecutive filings of the same ISIN. A company
  that changes ISIN (rare: demerger, merger) becomes a new company in `dim_company`.
- Spelling differences (case, `Ltd`/`Limited`, bracketed abbreviations) are cleaned first, so
  they are not mistaken for name changes.
