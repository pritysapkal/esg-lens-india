"""Build a tiny synthetic data folder so dbt staging can run in CI (no real NSE data there).

Usage:  python scripts/make_ci_data.py <out_dir>
Then:   ESG_DATA_DIR=<out_dir> DUCKDB_PATH=<out_dir>/ci.duckdb \
        dbt build --profiles-dir . --select staging --exclude tag:realdata   (from dbt/)

Creates, from tests/fixtures/synthetic_brsr.xml (fake company "Example Ltd"):
  <out_dir>/raw/manifest.csv
  <out_dir>/raw/reference/ind_nifty50list.csv
  <out_dir>/processed/listing.parquet
  <out_dir>/processed/parsed/<table>/reporting_year_label=2025-2026/<filing_id>.parquet
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion import config  # noqa: E402
from ingestion.discover import LISTING_COLUMNS, filing_id_from_url  # noqa: E402
from ingestion.intake import MANIFEST_COLUMNS, sha256_file  # noqa: E402
from ingestion.parse_xbrl import parse_all  # noqa: E402

FIXTURE = config.REPO_ROOT / "tests" / "fixtures" / "synthetic_brsr.xml"
YEAR = "2025-2026"


def build(out_dir: Path) -> None:
    raw, processed = out_dir / "raw", out_dir / "processed"
    (raw / "reference").mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    filing_id = filing_id_from_url("https://example.com/synthetic_brsr.xml")

    manifest = {col: "" for col in MANIFEST_COLUMNS} | {
        "filing_id": filing_id,
        "symbol": "EXAMPLE",
        "isin": "INE000X00000",
        "reporting_year_label": YEAR,
        "taxonomy_version": "2026-02-28",
        "file_name": FIXTURE.name,
        "sha256": sha256_file(FIXTURE),
        "bytes": FIXTURE.stat().st_size,
        "received_at": "2026-10-09T00:00:00+00:00",
        "path": FIXTURE.as_posix(),
        "matched_listing": True,
        "entity_identifier": "INE000X00000",
        "entity_identifier_scheme": "ISIN",
        "isin_source": "xbrl",
    }
    manifest_path = raw / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(manifest)

    (raw / "reference" / "ind_nifty50list.csv").write_text(
        "Company Name,Industry,Symbol,Series,ISIN Code\n"
        "Example Ltd.,Financial Services,EXAMPLE,EQ,INE000X00000\n",
        encoding="utf-8",
    )

    listing = {col: None for col in LISTING_COLUMNS} | {
        "symbol": "EXAMPLE",
        "company_name": "Example Limited",
        "fy_from": 2025,
        "fy_to": 2026,
        "reporting_year_label": YEAR,
        "is_non_standard_period": False,
        "submission_date": pd.Timestamp("2026-06-30").date(),
        "xbrl_file_name": FIXTURE.name,
        "filing_id": filing_id,
        "source_file": "synthetic",
    }
    frame = pd.DataFrame([listing], columns=LISTING_COLUMNS)
    frame["fy_from"] = frame["fy_from"].astype("Int64")
    frame["fy_to"] = frame["fy_to"].astype("Int64")
    frame["revision_date"] = frame["revision_date"].astype(object)
    frame.to_parquet(processed / "listing.parquet", index=False)

    summary = parse_all(manifest_path, processed / "parsed", processed / "parse_errors.csv")
    if summary.failed or len(summary.parsed) != 1:
        raise SystemExit(f"synthetic parse failed: {summary.failed}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/make_ci_data.py <out_dir>")
    out = Path(sys.argv[1]).resolve()
    build(out)
    print(f"synthetic data -> {out.as_posix()}")


if __name__ == "__main__":
    main()
