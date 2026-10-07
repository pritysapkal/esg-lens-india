"""Discover new or revised BRSR filings from the NSE listing.

Planned behaviour (implemented in a later week - this is a stub):

1. Read the NSE BRSR listing CSV(s) saved under ``data/raw/listing/`` (one row per filing:
   company symbol / name, ISIN, financial year, XBRL URL, submission date, revision flag).
2. Normalise columns; the company key is the **ISIN**.
3. Derive ``filing_id = sha256(xbrl_url)`` (hex). The URL uniquely identifies a submitted
   file, so a revised filing gets a new URL and therefore a new ``filing_id``.
4. Compare against the download manifest (``config.MANIFEST_PATH``) and return only filings
   that are new or revised (``filing_id`` not yet in the manifest).
5. Optionally restrict to the target universe (top ~1,000 companies by market cap, from the
   NSE market-cap ranking list - see docs/week1_open_questions.md).

Output: a DataFrame / list of ``Filing`` records consumed by ``ingestion.download``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def filing_id_from_url(xbrl_url: str) -> str:
    """Return the deterministic filing id: SHA-256 hex digest of the (stripped) XBRL URL."""
    return hashlib.sha256(xbrl_url.strip().encode("utf-8")).hexdigest()


def discover_filings(listing_csv: Path, manifest_path: Path | None = None):
    """Return filings in ``listing_csv`` that are not yet in the download manifest."""
    raise NotImplementedError("discover_filings is planned for week 2")


def main() -> None:
    raise NotImplementedError("discover is planned for week 2")


if __name__ == "__main__":
    main()
