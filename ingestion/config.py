"""Central configuration: loads `.env` and defines every filesystem path the pipeline uses.

All paths are absolute `pathlib.Path` objects. Relative values in `.env` are resolved
against the repository root, so scripts behave the same regardless of the working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / ".env")


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


# --- Data lake -----------------------------------------------------------------------------
DATA_DIR: Path = _resolve(os.getenv("DATA_DIR", "data"))
RAW_DIR: Path = DATA_DIR / "raw"
LISTING_DIR: Path = RAW_DIR / "listing"  # NSE BRSR listing CSVs (downloaded manually)
REFERENCE_DIR: Path = RAW_DIR / "reference"  # index constituent lists
UNIVERSE_CSV: Path = REFERENCE_DIR / "ind_nifty50list.csv"  # official NIFTY 50 constituents
XBRL_INBOX_DIR: Path = RAW_DIR / "xbrl_inbox"  # manually downloaded XBRL files land here
XBRL_DIR: Path = RAW_DIR / "xbrl"  # <ISIN>/<reporting_year_label>/<file> (never overwritten)
TAXONOMY_DIR: Path = RAW_DIR / "taxonomy"  # SEBI BRSR taxonomy packages, one per version
PROCESSED_DIR: Path = DATA_DIR / "processed"  # derived outputs (listing, taxonomy versions, ...)
WAREHOUSE_DIR: Path = DATA_DIR / "warehouse"
DUCKDB_PATH: Path = _resolve(os.getenv("DUCKDB_PATH", "data/warehouse/esg_lens.duckdb"))

MANIFEST_PATH: Path = RAW_DIR / "manifest.csv"  # sha256 intake manifest (append-only)
LISTING_PARQUET: Path = PROCESSED_DIR / "listing.parquet"
TAXONOMY_VERSIONS_CSV: Path = PROCESSED_DIR / "taxonomy_versions.csv"
PARSED_DIR: Path = PROCESSED_DIR / "parsed"  # <table>/reporting_year_label=<y>/<filing_id>.parquet
PARSE_ERRORS_CSV: Path = PROCESSED_DIR / "parse_errors.csv"

# --- Repo assets ---------------------------------------------------------------------------
FIXTURES_DIR: Path = REPO_ROOT / "fixtures"
XBRL_FIXTURES_DIR: Path = FIXTURES_DIR / "xbrl"
DBT_DIR: Path = REPO_ROOT / "dbt"
DOCS_DIR: Path = REPO_ROOT / "docs"
DATA_STATUS_MD: Path = DOCS_DIR / "data_status.md"

DATA_PATHS: tuple[Path, ...] = (
    LISTING_DIR,
    REFERENCE_DIR,
    XBRL_INBOX_DIR,
    XBRL_DIR,
    TAXONOMY_DIR,
    PROCESSED_DIR,
    WAREHOUSE_DIR,
)


def display_path(path: Path) -> str:
    """Return ``path`` relative to the repo root (POSIX style) if inside it, else absolute."""
    path = Path(path).resolve()
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
