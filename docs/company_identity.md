# Company identity and sectors

How a company is identified, named and classified in the warehouse (Module 5). Built by
`int_company_names`, `int_company_nic`, `dim_company` and `dim_company_history`, with the seeds
`nic_sector_map`, `nic_code_corrections`, `peer_groups` and `metric_materiality`.
Sector grouping, ranking rule and materiality were refined on 2026-10-10 (see below).
Numbers below are from the build of 2026-10-10 (51 companies, 196 filings).

## Identity

| Item | Rule |
|---|---|
| **Key** | **ISIN** of the equity share. One row per company in `dim_company`. All 196 filings carry an ISIN: filed in the FY2025-26 XBRL; for earlier years (CIN-identified files) taken from the same company's intake match. |
| **Symbol** | NSE symbol in the latest filing (`current_symbol`); every symbol seen is in `all_symbols`. Today each company has exactly one symbol. |
| **CIN** | `CorporateIdentityNumber` fact, kept only if it has the shape of a CIN. State Bank of India files placeholders (`Z99999ZZ9999ZZZ999999`, `A00000AA0000AAA000000`) as it is a statutory body, so its CIN is empty (`cin_filed` keeps the filed text). `99999` inside a CIN is a real "unclassified" industry code (L&T, SBI Life) and is kept. |
| **Name** | XBRL `NameOfTheCompany`; if it holds broken characters, the NSE listing name. Cleaning: broken characters removed, bracketed abbreviations removed (`State Bank of India (SBI/the Bank/Bank)` -> `State Bank of India`), `Ltd` -> `Limited`, ALL-CAPS replaced by the mixed-case spelling used in another year (title case if none). |
| **Years** | One name per ISIN and financial year; with several filings for a year the latest period end wins. |

### Name changes found

**None.** After cleaning, every company has one name and one symbol across all its filings, so
`dim_company_history` has 51 rows (one per company, all current).

- **Eternal (ETERNAL, INE758T01015):** filings exist for FY2024-25 and FY2025-26 only, both as
  "Eternal Limited". There is no Zomato-named filing in the set, so the Zomato -> Eternal change
  cannot be shown from the filings.
- **Tata Motors Passenger Vehicles (TMPV, INE155A01022):** one filing, FY2025-26. The pre-demerger
  Tata Motors filings are not in the set. The ISIN INE155A01022 is the one confirmed by the
  NIFTY 50 file.
- Differences seen in raw names were only spelling: ALL-CAPS (APOLLOHOSP, BAJAJ-AUTO, BEL, BSE,
  DRREDDY, HINDALCO, JSWSTEEL, KOTAKBANK, NTPC, SBIN), `Ltd` vs `Limited` (M&M), bracketed
  abbreviations (SBIN, SHRIRAMFIN, SUNPHARMA) and broken characters (SBIN FY2025-26 in the
  listing). Three companies were ALL-CAPS in every filing and are title-cased: Coal India, Eicher
  Motors, Max Healthcare Institute.

Method and why this is not a dbt snapshot: [ADR 0003](adr/0003-company-history-scd2.md).

## NIC sector

Source: the BRSR table of products or services accounting for 90% of turnover. Per row the filing
has a NIC code (`NICCodeOfProductOrServiceSoldByTheEntity`), its turnover share
(`PercentageOfTotalTurnoverForProductOrServiceSold`) and a description. They sit in the same
context (same dimension member), so they are paired on it. 195 of 196 filings have the table
(Coal India FY2022-23 does not); 513 rows.

1. **Cleaning.** Digits only. Codes are typed by hand and often wrong, so
   `nic_code_corrections` (seed, 16 rows, `verified_by` empty for your review) holds explicit
   fixes: dropped leading zeros (`6101` -> `06101` for Reliance's offshore petroleum rows,
   `510` -> `0510` for Coal India), concatenated codes (`292726302008`, `6201362020`), `2008` (the
   NIC edition year typed as a code, BEL) and `9993` (Max Healthcare, not a NIC code). A code with
   fewer than 2 digits or all zeros (`0`: "Others", "Income from services") is *unclassified*: it
   keeps its share but has no division.
2. **Primary NIC** = the code with the highest turnover share in the company's **latest filing
   that has usable NIC data** (all 51 companies have FY2025-26). Rows with the same code in one
   filing are added up first (HCLTech files three rows, all `620`). Ties -> lowest code.
3. **Division** = first two digits of the code. `nic_division_name` comes from the
   `nic_sector_map` seed.
4. **Conglomerate** (`is_conglomerate`) = the largest NIC *division* is below 60% of turnover,
   **or** 3 or more divisions have at least 15% each. Division, not code, is used for the share
   test so that a company with many sub-codes inside one industry (Reliance's refining and
   chemicals, HUL's home care) is not called a conglomerate for that alone.
5. **Shares are as filed.** Filings are not forced to sum to 100%: the 90%-of-turnover table
   legitimately sums to about 90%. FY2025-26 totals range from 0.86 (Trent) to 1.0.

### NIC divisions found

42 divisions appear in the data (all in `nic_sector_map`, source "NIC-2008, MoSPI"):
05, 06, 07, 10, 11, 12, 14, 15, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 32, 35, 36,
41, 42, 45, 46, 47, 51, 52, 55, 61, 62, 63, 64, 65, 66, 74, 82, 85, 86. 169 distinct codes.
The division names are written from NIC-2008 from memory and **need your check**: the
`verified_by` column is empty on purpose.

### Conglomerates (5)

| Symbol | Top division share | Divisions >= 15% | Top 3 codes (share) |
|---|---|---|---|
| ADANIENT | 28.4% | 3 | 46610 (28.4%); 27900 (15.3%); 24201 (15.2%) |
| BEL | 47.0% | 2 | 2630 (30.0%); 2927 (20.0%); 2651 (17.0%) |
| ITC | 45.9% | 2 | 120004 (45.9%); 103003 (29.9%); 102099 (15.2%) |
| APOLLOHOSP | 56.7% | 2 | 861001 (56.7%); 464907 (42.3%) |
| CIPLA | 57.2% | 2 | 210002 (55.6%); 464907 (42.8%); 210001 (1.6%) |

APOLLOHOSP and CIPLA are flagged only because pharmacy / wholesale (464907, about 43%) sits next
to their main business; BEL because `2008` could not be used (23% unclassified).

## Source priority

1. **Peer group and sector group come from the NSE industry**, assigned in the `peer_groups` seed
   (an analyst mapping of the NSE industry to nine groups). This is the primary source.
2. **NIC primary division is a cross-check only.** It is never used to assign a group. The column
   `nic_agrees_with_peer_group` in `dim_company` says whether the division points to the same
   group (via `expected_peer_group` in `nic_sector_map`).
3. **Decision (reviewed 2026-10-10):** the sector conflicts below were reviewed and **all current
   peer groups are kept**. Conflicts are expected for conglomerates and for consumer brands that
   file chemical NIC codes (paints, soaps).

## Peer groups, sector groups and the ranking rule

Two levels: nine **peer groups**, rolled up into three **sector groups**. A company is ranked in
its peer group only if that has **at least 5 companies and is not "Industrials & others"**;
otherwise it is ranked in its sector group (`ranking_group`, `ranking_basis`).

| Peer group | Sector group | n | Ranking group | Ranking basis | Symbols |
|---|---|---:|---|---|---|
| Financials | Financials | 12 | Financials | peer_group | AXISBANK, BAJAJFINSV, BAJFINANCE, BSE, HDFCBANK, HDFCLIFE, ICICIBANK, JIOFIN, KOTAKBANK, SBILIFE, SBIN, SHRIRAMFIN |
| Consumer | Asset-light | 8 | Consumer | peer_group | ASIANPAINT, ETERNAL, HINDUNILVR, ITC, NESTLEIND, TATACONSUM, TITAN, TRENT |
| IT services | Asset-light | 5 | IT services | peer_group | HCLTECH, INFY, TCS, TECHM, WIPRO |
| Healthcare | Asset-light | 5 | Healthcare | peer_group | APOLLOHOSP, CIPLA, DRREDDY, MAXHEALTH, SUNPHARMA |
| Energy & utilities | Asset-heavy | 5 | Energy & utilities | peer_group | COALINDIA, NTPC, ONGC, POWERGRID, RELIANCE |
| Automobiles | Asset-heavy | 5 | Automobiles | peer_group | BAJAJ-AUTO, EICHERMOT, M&M, MARUTI, TMPV |
| Metals & mining | Asset-heavy | 4 | Asset-heavy | sector_group | ADANIENT, HINDALCO, JSWSTEEL, TATASTEEL |
| Cement & construction | Asset-heavy | 3 | Asset-heavy | sector_group | GRASIM, LT, ULTRACEMCO |
| Industrials & others | Asset-heavy | 4 | Asset-heavy | sector_group | ADANIPORTS, BEL, BHARTIARTL, INDIGO |

Resulting ranking groups: Financials 12, Asset-heavy 11, Consumer 8, Healthcare 5, IT services 5,
Energy & utilities 5, Automobiles 5 - none below 5 (tested). "Industrials & others" carries
`caution_note`: *heterogeneous group: defence, ports, airline, telecom - not peer-ranked*.

WIPRO is not in the NIFTY 50 file (`in_universe = false`, `nse_industry` empty); its group and
`sub_industry` (Information Technology, set by hand) come from the seed.

**Sub-industry** (`sub_industry`): Financials are split into Banks (5: HDFCBANK, ICICIBANK,
AXISBANK, KOTAKBANK, SBIN), NBFC (4: BAJFINANCE, SHRIRAMFIN, BAJAJFINSV, JIOFIN), Insurance (2:
SBILIFE, HDFCLIFE) and Market infrastructure (1: BSE). Other companies carry their NSE industry.
Ranking stays at Financials level; the sub-industry is for filtering and context.

## Sector conflicts (cross-check, reviewed - all peer groups kept)

Companies where `nic_agrees_with_peer_group = false`. Nothing is changed automatically.

| Symbol | Peer group | NSE industry | Primary NIC | NIC division | Top 3 NIC codes (share) |
|---|---|---|---|---|---|
| ADANIENT | Metals & mining | Metals & Mining | 46610 | 46 Wholesale trade | 46610 (28.4%); 27900 (15.3%); 24201 (15.2%) |
| ASIANPAINT | Consumer | Consumer Durables | 202 | 20 Chemicals | 202 (94.7%) |
| ETERNAL | Consumer | Consumer Services | 63999 | 63 Information service activities | 63999 (93.0%) |
| GRASIM | Cement & construction | Construction Materials | 2030 | 20 Chemicals | 2030 (42.0%); 4690 (31.0%); 2011 (23.0%) |
| HINDUNILVR | Consumer | Fast Moving Consumer Goods | 202302 | 20 Chemicals | 202302 (36.9%); 107601 (23.9%); 202306 (21.7%) |

The conglomerates (ADANIENT, BEL, ITC, APOLLOHOSP, CIPLA) are listed above under NIC sector; only
ADANIENT also disagrees on division.

## Materiality

Seed `metric_materiality` (peer group x metric, 306 rows; edit the CSV to change). **Not
material = shown but not ranked.** Default is material; each row has a `reason`.

| Peer group | Not material (27 rows in total) | Why |
|---|---|---|
| Financials | GHG Scope 1, 2, 3 and intensity; energy (total, renewable, intensity); water (withdrawal, consumption, intensity); waste (generated, recovered, disposed); LTIFR, fatalities, recordable injuries; MSME sourcing; days payable (18 metrics) | Own operations are office-based; financed emissions are not in BRSR |
| IT services | Water (3); waste (3); LTIFR, fatalities, recordable injuries (3) | Office-based: small, not decision-relevant. GHG Scope 1/2, intensity, energy and renewable energy **are material** (electricity is the main footprint; SASB treats energy as material for software and IT services) |
| Healthcare | none | Effluents, hazardous and biomedical waste: all environmental metrics material, safety material |
| Consumer, Energy & utilities, Metals & mining, Cement & construction, Automobiles, Industrials & others | none | Everything material |

Gender, wellbeing, attrition, POSH, data breaches, related-party %, assurance and boundary metrics
are material for every group. `int_metric_values_enriched` adds `company_name`, `peer_group`
and `is_material` to every metric value (21,730 rows).

## Company-year grain (`dim_company_year`)

One row per company (ISIN) and financial year, from the latest filing of that year: 196 rows
(= the 196 filings). It is the grain every yearly fact and score joins to.

| Column group | Columns |
|---|---|
| Keys | `isin`, `fiscal_year_label`, `filing_id` (latest filing of the year) |
| Names and groups | `symbol`, `display_name`, `peer_group`, `sector_group`, `ranking_group`, sort keys `peer_group_sort`, `sector_group_sort` |
| Period | `period_start`, `period_end`, `period_months`, `is_non_standard_period`, `annualisation_factor` (12 / months), `taxonomy_version` |
| Basis | `reporting_boundary` (standalone / consolidated) |
| Size | `turnover_inr` (corrected), `total_headcount`, `size_band`, `size_band_basis` |
| Quality | `brsr_core_assurance_status` (assured / assessed / not disclosed), `has_comparability_break` |

- **Annualisation:** NESTLEIND's 15-month year (FY2023-24) has factor 0.8. Multiply flows by it to
  compare with 12-month years; ratios need no change.
- **Headcount** = employees + workers, permanent and other than permanent (the "Employees" and
  "Workers" totals of the headcount table; checked to equal the sum of the four parts).
- **Assurance** is only filed in FY2024-25 and FY2025-26 (`dim_fiscal_year.assurance_fields_available`);
  earlier years show "not disclosed", which is *not applicable*, not a failure.
- **Boundary changes within a company** exist (NTPC, POWERGRID, TATACONSUM, TATASTEEL, WIPRO
  switch between standalone and consolidated); values across such years are not like for like.

### Size band method

Tercile of the size measure **within sector group and fiscal year** (Large = top third, Mid,
Small), with `size_band_basis` saying which measure:

- **Asset-light and Asset-heavy:** `turnover_inr`.
- **Financials:** `total_headcount`, because a bank's "turnover" (interest income plus fees) is not
  comparable with an insurer's or an exchange's.
- Ties break by ISIN; a company with a missing measure has no band and does not distort the
  terciles. Terciles are relative to the NIFTY 50 sample, not to the market.

Example split over all years (INR crore): Asset-light Small < 20,500, Mid up to 55,000, Large above;
Asset-heavy Small < 81,000, Mid up to 138,000, Large above; Financials by headcount Small < 43,200,
Mid up to 124,300, Large above (ranges overlap slightly because terciles are cut per year).

## Structural breaks (`corporate_events`)

Seed of mergers, demergers, renames and acquisitions. `comparability_break = true` on the
affected year sets `has_comparability_break` in `dim_company_year`; downstream trend and
restatement logic must not treat that year-on-year change as performance.

| Company | Event | Effective | Affects | Break |
|---|---|---|---|---|
| HDFCBANK | Merger with HDFC Ltd | 2023-07-01 | FY2023-24 | true |
| RELIANCE | Demerger of financial services (Jio Financial) | 2023-07-01 | FY2023-24 | true |
| JIOFIN | Demerged from Reliance; first filing year | 2023-07-01 | FY2023-24 | false (no prior year) |
| ITC | Hotels demerger (ITC Hotels) | 2025-01-01 | FY2024-25 | true |
| TMPV | Commercial-vehicle demerger; keeps INE155A01022 | not given | FY2025-26 | true |
| ETERNAL | Zomato renamed Eternal | 2025 (day not given) | FY2024-25 | false |
| SHRIRAMFIN | Merger of Shriram Transport and Shriram City Union | 2022-12 | FY2022-23 | true |

All rows have `verified = false`; they come from the analyst brief and have not been checked
against company announcements. No other rename was found in `dim_company_history`. Suspected
further events (large year-on-year jumps) are listed in the build report for review, not added.

## Ownership and business group (`company_attributes`)

`display_name` (short name for charts), `ownership_type` (Government 7, Private Indian 41,
MNC subsidiary 3) and `business_group` (Tata 6, Independent 27, Bajaj 3, Aditya Birla 3, HDFC 2,
Mahindra 2, Reliance 2, SBI 2, Adani 2, Bharti 1, JSW 1). Seed values come from the analyst brief;
"Independent" is the default for companies not in the brief's group list, and the doubtful cases
(SBILIFE, ITC, TITAN, SHRIRAMFIN, EICHERMOT, MAXHEALTH) say so in `source_note`.
All rows have `verified = false`.

WIPRO's `sub_industry` (Information Technology) is **verified** by the project owner (2026-10-10).

## Fiscal years (`dim_fiscal_year`)

FY2022-23 to FY2025-26, April to March, with `is_brsr_core_year` (FY2023-24 onwards) and
`assurance_fields_available` (FY2024-25 onwards). `dim_company_year` and `corporate_events` relate
to it on `fiscal_year_label`. Whether a metric must be disclosed in a year is in
`metric_disclosure_requirement` (see [business rules](business_rules.md)).

## Power BI columns

`display_name`, `peer_group_sort`, `sector_group_sort` (Financials 1, Asset-light 2, Asset-heavy 3;
peer groups in the order of the groups table) are in `dim_company` and `dim_company_year` so visuals
can sort and label without extra tables.

## Known limitations

- **Survivorship bias.** `universe_basis` is *NIFTY 50 constituents as of 2026-10 (applied to all
  years)*. Companies that left the index before October 2026 are not in the data, and companies
  that joined recently (JIOFIN, ETERNAL, TMPV, BSE) are held to the same list for years in which
  they were not constituents. Averages and rankings over FY2022-23 to FY2025-26 therefore describe
  today's large companies, not the index as it was; weak or delisted companies are missing.
- **Industrials & others is heterogeneous** (defence, ports, an airline, telecom). It is not
  peer-ranked; these four are ranked in the Asset-heavy sector group and carry a caution note.
- **Small peer groups.** Metals & mining (4) and Cement & construction (3) fall back to the
  sector group; Asset-heavy rankings mix them with Industrials & others.
- **Sector is an NSE-industry mapping**, not a company's exact business; NIC data only cross-checks it.
- NIC division names and code corrections are unverified (`verified_by` empty).
- **Event, ownership and group seeds need human verification** (`verified = false`): the structural-break flags and groups rest on the analyst brief, and TMPV, ETERNAL and SHRIRAMFIN have no exact effective date.
- **Comparability beyond the listed events is not detected.** Large jumps in turnover or headcount can also come from boundary changes (standalone vs consolidated) or filing errors, e.g. BAJAJFINSV turnover swings between about 1,700 and 134,000 crore across years and is a data-quality question, not a business change.

## Tests

dbt tests cover: unique / not-null ISIN, every metric-value ISIN exists in `dim_company`, accepted
peer groups, no overlapping history and one current row per ISIN, unique symbols and codes in the
seeds, and every NIC division in `dim_company` exists in `nic_sector_map`. Singular real-data tests
(tag `realdata`, skipped in CI): HDFCBANK is Financials / division 64, TMPV has ISIN
INE155A01022, ETERNAL history has only Eternal / Zomato names, and the 51 symbols are covered.
