# ADR 0002 - Manual intake of NSE files (NSE terms of use)

- **Status:** Accepted
- **Date:** 2026-10-08
- **Supersedes:** the "Ingestion HTTP (httpx + tenacity)" row of [ADR 0001](0001-tech-stack.md)

## Context

The original plan was a polite, rate-limited downloader that fetched BRSR XBRL files from
`nsearchives.nseindia.com`. The [NSE Terms of Use](https://www.nseindia.com/static/nse-terms-of-use)
(updated 29/10/2025) rule this out:

- **Clause 9** prohibits "systematic or automated data collection activities (including
  scraping, data mining, data extraction and data harvesting)". Rate limiting does not change
  this.
- **Clause 8** prohibits redistributing the content without NSE's written permission.

The scope is the NIFTY 50: 51 companies and 197 listed filings for FY2022-23 to FY2025-26. At
this size, manual download takes roughly an hour per year of filings.

## Decision

1. **Manual download only.** A person downloads each company's BRSR listing CSV and its XBRL
   files from the NSE website. The files go into `data/raw/listing/` and `data/raw/xbrl_inbox/`.
2. **No network code for NSE.** No module makes HTTP requests to `nseindia.com` or
   `nsearchives.nseindia.com`. `ingestion/download.py` was deleted, and `httpx`/`tenacity` are
   no longer direct dependencies. A smoke test fails if an HTTP client is imported in
   `ingestion/`.
3. **Local intake.** `python -m ingestion.intake` checks each inbox file (sha256, ISIN and
   taxonomy version read from the XML) and matches it to the listing by exact file name. It then
   moves the file to `data/raw/xbrl/<ISIN>/<reporting_year_label>/` and appends to
   `data/raw/manifest.csv`. It never overwrites a file, and running it again changes nothing.
4. **No redistribution of raw files.** All of `data/` is git-ignored, and real XBRL files are
   never committed. Tests use a hand-written synthetic instance. Tests that need real data skip
   when it is absent.
5. **Publish derived metrics only.** Any published output (dashboards, app, docs) shows computed
   metrics and links to the source filing on NSE. It never shows the raw file.

## Consequences

- New filings appear only when someone downloads them. `docs/data_status.md` (written by
  `python -m ingestion.todo`) lists what is listed, received, missing or unavailable.
- Orchestration (Airflow, week 13) watches the inbox. It does not download.
- CI and other clones cannot rebuild the warehouse without their own manual download. This is
  expected: the repo ships code, synthetic fixtures and derived outputs, not NSE data.
- A file that NSE lists but does not serve is recorded as `listed_unavailable` and is not
  retried. The known case is M&M FY2023-24, `BRSR_1167401_29062024075519_WEB.xml`.

## Revisit when

- NSE grants **written permission** for automated access or redistribution (for example under a
  data licence). An automated fetcher could then feed the same inbox, and intake would stay as it
  is.
- The scope grows well beyond the NIFTY 50, so that manual download is no longer practical. In
  that case, look for a licensed data source before writing any automation.
