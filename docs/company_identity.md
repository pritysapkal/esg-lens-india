# Company identity and sectors

How a company is identified, named and classified in the warehouse (Module 5). Built by
`int_company_names`, `int_company_nic`, `dim_company` and `dim_company_history`, with the seeds
`nic_sector_map`, `nic_code_corrections`, `peer_groups` and `metric_materiality`.
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

## Peer groups

Seed `peer_groups` (symbol -> group), nine groups, your proposal v1. All 51 symbols are assigned
exactly once; **no symbol was missing from your list**, and none is assigned twice.

| Peer group | Companies | Symbols |
|---|---:|---|
| Financials | 12 | AXISBANK, BAJAJFINSV, BAJFINANCE, BSE, HDFCBANK, HDFCLIFE, ICICIBANK, JIOFIN, KOTAKBANK, SBILIFE, SBIN, SHRIRAMFIN |
| Consumer | 8 | ASIANPAINT, ETERNAL, HINDUNILVR, ITC, NESTLEIND, TATACONSUM, TITAN, TRENT |
| IT services | 5 | HCLTECH, INFY, TCS, TECHM, WIPRO |
| Healthcare | 5 | APOLLOHOSP, CIPLA, DRREDDY, MAXHEALTH, SUNPHARMA |
| Energy & utilities | 5 | COALINDIA, NTPC, ONGC, POWERGRID, RELIANCE |
| Automobiles | 5 | BAJAJ-AUTO, EICHERMOT, M&M, MARUTI, TMPV |
| Metals & mining | 4 | ADANIENT, HINDALCO, JSWSTEEL, TATASTEEL |
| Industrials & others | 4 | ADANIPORTS, BEL, BHARTIARTL, INDIGO |
| Cement & construction | 3 | GRASIM, LT, ULTRACEMCO |
| **Total** | **51** | |

WIPRO is not in the NIFTY 50 file (`in_universe = false`, `nse_industry` empty); its peer group
comes from the seed like all the others. The peer group is **never** derived from NIC or NSE
industry: those are only used to flag conflicts.

## Sector conflicts (for your review)

Companies whose primary NIC division does not point to their peer group (`expected_peer_group`
column of `nic_sector_map`, an analyst hint), plus the conglomerates. Nothing is changed
automatically.

| Symbol | Peer group | NSE industry | Primary NIC | NIC division | Division would suggest | Top 3 NIC codes (share) |
|---|---|---|---|---|---|---|
| ADANIENT | Metals & mining | Metals & Mining | 46610 | 46 Wholesale trade | Consumer | 46610 (28.4%); 27900 (15.3%); 24201 (15.2%) |
| ASIANPAINT | Consumer | Consumer Durables | 202 | 20 Chemicals | Industrials & others | 202 (94.7%) |
| ETERNAL | Consumer | Consumer Services | 63999 | 63 Information service activities | IT services | 63999 (93.0%) |
| GRASIM | Cement & construction | Construction Materials | 2030 | 20 Chemicals | Industrials & others | 2030 (42.0%); 4690 (31.0%); 2011 (23.0%) |
| HINDUNILVR | Consumer | Fast Moving Consumer Goods | 202302 | 20 Chemicals | Industrials & others | 202302 (36.9%); 107601 (23.9%); 202306 (21.7%) |
| BEL | Industrials & others | Capital Goods | 2630 | 26 Electronics | Industrials & others | 2630 (30.0%); 2927 (20.0%); 2651 (17.0%) - conglomerate |
| ITC | Consumer | Fast Moving Consumer Goods | 120004 | 12 Tobacco | Consumer | 120004 (45.9%); 103003 (29.9%); 102099 (15.2%) - conglomerate |
| APOLLOHOSP | Healthcare | Healthcare | 861001 | 86 Human health | Healthcare | 861001 (56.7%); 464907 (42.3%) - conglomerate |
| CIPLA | Healthcare | Healthcare | 210002 | 21 Pharmaceuticals | Healthcare | 210002 (55.6%); 464907 (42.8%); 210001 (1.6%) - conglomerate |

Reading: the five hard conflicts are the ones to decide. ASIANPAINT, GRASIM and HINDUNILVR file
chemicals (division 20) codes for products you group under Consumer / Cement. ETERNAL files an
information-service code for a food-delivery platform; Consumer is the better group. ADANIENT's
largest line is trading (46), not metals.

## Materiality

Seed `metric_materiality` (peer group x metric, 306 rows; edit the CSV to change):

- Not material (shown, not ranked) for **Financials** and **IT services**: energy
  (`energy_*`), water (`water_*`), waste (`waste_*`) quantities and filed intensities, and GHG
  intensity (`ghg_intensity_*`). That is 10 metrics x 2 groups = 20 rows set to `false`.
- Everything else is material for every group: absolute GHG emissions, all social and
  governance metrics (safety, gender, wellbeing, inclusion, fairness, openness), turnover and
  the disclosure-quality metrics.
- `int_metric_values_enriched` adds `company_name`, `peer_group` and `is_material` to every
  metric value (21,730 rows, 1,337 not material).

## Tests

dbt tests cover: unique / not-null ISIN, every metric-value ISIN exists in `dim_company`, accepted
peer groups, no overlapping history and one current row per ISIN, unique symbols and codes in the
seeds, and every NIC division in `dim_company` exists in `nic_sector_map`. Singular real-data tests
(tag `realdata`, skipped in CI): HDFCBANK is Financials / division 64, TMPV has ISIN
INE155A01022, ETERNAL history has only Eternal / Zomato names, and the 51 symbols are covered.
