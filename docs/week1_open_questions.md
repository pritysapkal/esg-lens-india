# Week 1 - open questions

All four questions are answered. Counts come from the listing CSVs and the intake manifest as of
2026-10-08 (see `docs/data_status.md`, regenerated with `python -m ingestion.todo`).

| # | Question | Status |
|---|---|---|
| 1 | How far back do NSE BRSR **XBRL** files go? | Answered |
| 2 | What do the **NSE terms of use** say about automated downloads? | Answered |
| 3 | What is the exact filename / URL of the NSE market-cap ranking list (top 1,000)? | Superseded |
| 4 | Are **older SEBI BRSR taxonomy versions** still downloadable? | Answered |

## Q1 - How far back do NSE BRSR XBRL files go?

**Status: Answered.** XBRL is available from **FY2022-23** for almost all NIFTY 50 companies.
The listing CSVs contain **197 filings for 51 companies** (the 50 constituents plus WIPRO):

| Reporting year | Listed filings |
|---|---:|
| 2022-2023 | 47 |
| 2023-2024 | 49 |
| 2024-2025 | 50 |
| 2025-2026 | 51 |

47 companies have all 4 years. The exceptions are real, not data errors:

- **NESTLEIND - 3 filings.** Nestle India moved from a calendar year to April-March; its
  2023-2024 filing covers a 15-month period (the XBRL current-year context starts 2023-01-01).
- **JIOFIN - 3 filings.** Jio Financial Services listed in August 2023.
- **ETERNAL - 2 filings.** Older filings sit under the former name Zomato.
- **TMPV - 1 filing.** Tata Motors Passenger Vehicles, renamed after the 2025 demerger; its ISIN
  INE155A01022 is the old Tata Motors ISIN.
- **M&M 2023-2024** (`BRSR_1167401_29062024075519_WEB.xml`) is listed but NSE returns an error
  for the file: recorded as `listed_unavailable`. So **196 of 197** listed filings are received.

Reporting periods are not assumed to be April-March: each filing carries
`reporting_year_label = f"{fy_from}-{fy_to}"`, and real period lengths will come from XBRL contexts.

## Q2 - What do the NSE terms of use say about automated downloads?

**Status: Answered.** Source: [NSE Terms of Use](https://www.nseindia.com/static/nse-terms-of-use),
updated 29/10/2025.

- **Clause 9** prohibits "systematic or automated data collection activities (including
  scraping, data mining, data extraction and data harvesting)".
- **Clause 8:** "User agrees that any information or content or data on the Website / Mobile
  Application shall not be copied, modified, reverse engineer, reproduced, uploaded, transmitted,
  posted, stored (either in hardcopy or in an electronic retrieval system), adapted, altered,
  translated, disseminated, distributed, displayed, performed, broadcasted, published,
  hyperlinked, sold, marketed, licensed, rented, leased or distributed in any form, without prior
  written permission of NSE. Unless the information or Content is available for download, not to
  aggregate, copy or duplicate in any manner any of the content or information which is available
  on Website / Mobile Application."

**Decision** (recorded in [ADR 0002](adr/0002-manual-intake-nse-terms.md)):

- Listing CSVs and XBRL files are **downloaded manually** by a person, through the website.
- The code makes **no automated requests** to `nseindia.com` or `nsearchives.nseindia.com`;
  the downloader stub and the HTTP dependencies were removed.
- **Raw files are not redistributed**: `data/` is git-ignored, and tests use synthetic fixtures.
- The project publishes **derived metrics only**, each with a link to the source filing on NSE.

## Q3 - Exact filename / URL of the NSE market-cap ranking list?

**Status: Superseded.** The universe is now the **official NIFTY 50 constituents** list from
niftyindices.com (`ind_nifty50list.csv`, saved to `data/raw/reference/`) instead of the
top-1,000 market-cap list. The smaller scope keeps manual intake practical.

## Q4 - Are older SEBI BRSR taxonomy versions still downloadable?

**Status: Answered.** Yes. NSE's "Taxonomy Archives" zip (`Taxonomy_Archives_20260731164437.zip`)
contains the older BRSR taxonomies. Downloaded versions: **2021-09-30, 2023-06-30, 2024-04-30,
2025-05-31**, plus the current **2026-02-28** (`Taxonomy_BRSR_20260330194931.zip`).

The filings in our dataset use exactly these 5 versions (from the schemaRef
`in-capmkt-ent-<version>.xsd`):

| Taxonomy version | Filings |
|---|---:|
| 2021-09-30 | 31 |
| 2023-06-30 | 16 |
| 2024-04-30 | 49 |
| 2025-05-31 | 49 |
| 2026-02-28 | 51 |
| **Total** | **196** |

Finding from intake: only filings on **2026-02-28** identify the company by ISIN. Older versions
use the `CorporateIdentityNumber` scheme. That is a CIN, or a dummy value for SBI. Intake keeps
the raw identifier and resolves the ISIN separately (see `ingestion/intake.py`).
