"""Polite, idempotent downloader for BRSR XBRL files from NSE.

Planned behaviour (implemented in a later week - this is a stub):

- Input: filings returned by ``ingestion.discover`` (``filing_id``, ISIN, FY, ``xbrl_url``).
- HTTP via ``httpx`` with ``config.USER_AGENT``; wait ``config.REQUEST_DELAY_SECONDS``
  between requests (rate-limited, single connection - never hammer NSE).
- Retries with ``tenacity``: exponential backoff + jitter on timeouts / 429 / 5xx;
  give up (and log) on 4xx other than 429.
- Save to ``data/raw/xbrl/<ISIN>/<filing_id>.xml``. **Never overwrite** an existing file:
  if the path exists, skip it. Write to a ``.part`` temp file and rename atomically.
- Compute SHA-256 of the saved bytes and append a row to the manifest
  (``config.MANIFEST_PATH``): filing_id, isin, fy, xbrl_url, local_path, sha256,
  bytes, http_status, downloaded_at (UTC ISO-8601).
- Respect NSE terms of use (see docs/week1_open_questions.md).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download_filings(filings) -> None:
    """Download each filing that is not already on disk and record it in the manifest."""
    raise NotImplementedError("download_filings is planned for week 2")


def main() -> None:
    raise NotImplementedError("download is planned for week 2")


if __name__ == "__main__":
    main()
