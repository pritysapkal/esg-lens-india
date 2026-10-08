# How to add filings

The NSE terms of use forbid automated collection, so new BRSR filings are added by hand
([ADR 0002](adr/0002-manual-intake-nse-terms.md)). The code never contacts NSE.

## Routine

1. **Download the company's listing CSV** from the NSE BRSR page (Corporate Filings ->
   Business Responsibility and Sustainability Reports), filtered to the company.
   Save it unchanged to `data/raw/listing/`. Keep NSE's file name
   (`CF-BRSR-equities-<SYMBOL>-<from>-to-<to>.csv`), because the symbol is read from it.
   If a newer CSV for the same company covers the same filings, it can sit next to the old
   one: filings are de-duplicated on the XBRL URL.
2. **Download the XBRL files** linked in that CSV's XBRL column. Save them unchanged, with
   their **original names**, to `data/raw/xbrl_inbox/`.
3. **Run intake:**

   ```powershell
   .\scripts\dev.ps1 intake      # Linux/CI: make intake
   ```

   This rebuilds `data/processed/listing.parquet` and `data/processed/taxonomy_versions.csv`.
   It then moves each matched file to `data/raw/xbrl/<ISIN>/<reporting_year_label>/` and
   appends it to `data/raw/manifest.csv`. Read the output:
   - **unmatched**: the file name is not in any listing CSV (re-download the CSV), or the file
     is not readable XBRL. These files stay in the inbox.
   - **already received**: the same bytes are already in the manifest. Delete the inbox copy.
   - **WARNING taxonomy ... has no folder**: download that taxonomy version (step 5).
4. **Update the status page:**

   ```powershell
   .\scripts\dev.ps1 todo        # Linux/CI: make todo
   ```

   Check the totals in `docs/data_status.md` and commit the updated file. It contains only
   names, years and file names, so it is safe to commit.
5. **New taxonomy version?** Download the SEBI BRSR taxonomy zip from NSE and keep it in
   `data/raw/taxonomy/`. Extract it to `data/raw/taxonomy/<version>/`. Any inner folder layout
   works: versions are found by searching for `in-capmkt-ent-<version>.xsd`.

## Rules

- Never rename or edit downloaded files. Intake matches on the exact file name and records
  the sha256.
- Never commit anything under `data/`, and never commit real XBRL to `fixtures/`.
- If NSE lists a filing but returns an error for the file, add it to `KNOWN_UNAVAILABLE` in
  `ingestion/discover.py` so that it shows as `listed_unavailable`.
- If the company is new to the NIFTY 50, also replace `data/raw/reference/ind_nifty50list.csv`
  with the current list from niftyindices.com.
