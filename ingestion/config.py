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


# --- HTTP ----------------------------------------------------------------------------------
USER_AGENT: str = os.getenv("USER_AGENT", "ESG-Lens-India/0.1 (capstone research)")
REQUEST_DELAY_SECONDS: float = float(os.getenv("REQUEST_DELAY_SECONDS", "2.5"))

# --- Data lake -----------------------------------------------------------------------------
DATA_DIR: Path = _resolve(os.getenv("DATA_DIR", "data"))
RAW_DIR: Path = DATA_DIR / "raw"
LISTING_DIR: Path = RAW_DIR / "listing"  # NSE BRSR listing CSVs
XBRL_DIR: Path = RAW_DIR / "xbrl"  # downloaded BRSR XBRL instance files (never overwritten)
TAXONOMY_DIR: Path = RAW_DIR / "taxonomy"  # SEBI BRSR taxonomy packages, one per version
PROCESSED_DIR: Path = DATA_DIR / "processed"  # Parquet outputs of parse_xbrl
WAREHOUSE_DIR: Path = DATA_DIR / "warehouse"
DUCKDB_PATH: Path = _resolve(os.getenv("DUCKDB_PATH", "data/warehouse/esg_lens.duckdb"))

MANIFEST_PATH: Path = XBRL_DIR / "manifest.csv"  # sha256 download manifest

# --- Repo assets ---------------------------------------------------------------------------
FIXTURES_DIR: Path = REPO_ROOT / "fixtures"
XBRL_FIXTURES_DIR: Path = FIXTURES_DIR / "xbrl"
DBT_DIR: Path = REPO_ROOT / "dbt"

DATA_PATHS: tuple[Path, ...] = (
    LISTING_DIR,
    XBRL_DIR,
    TAXONOMY_DIR,
    PROCESSED_DIR,
    WAREHOUSE_DIR,
)
