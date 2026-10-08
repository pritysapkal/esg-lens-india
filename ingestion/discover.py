"""Load the NSE BRSR listing CSVs (downloaded manually) into one normalised table.

Each file in ``data/raw/listing/`` is named ``CF-BRSR-equities-<SYMBOL>-<from>-to-<to>.csv``
and lists one row per BRSR filing of that company. The CSVs have quirks that are handled here:

- UTF-8 with BOM; header cells carry trailing newlines / spaces; the XBRL column is ``**XBRL``.
- Dates look like ``05-Oct-2026``; ``-`` means "no revision".
- There is no ISIN column: the symbol comes from the file name, the ISIN from the XML later.

Reporting periods are NOT assumed to be April-March (e.g. NESTLEIND's 2023-2024 filing covers
15 months), so ``reporting_year_label`` is simply ``f"{fy_from}-{fy_to}"`` and
``is_non_standard_period`` flags any span other than one year.

This module never makes network requests (see docs/adr/0002-manual-intake-nse-terms.md).
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion import config

COLUMN_MAP: dict[str, str] = {
    "COMPANY": "company_name",
    "FROM YEAR": "fy_from",
    "TO YEAR": "fy_to",
    "ATTACHMENT": "pdf_url",
    "XBRL": "xbrl_url",
    "ORIGINAL SUBMISSION DATE": "submission_date",
    "LATEST REVISION DATE": "revision_date",
}

LISTING_COLUMNS: list[str] = [
    "symbol",
    "company_name",
    "fy_from",
    "fy_to",
    "reporting_year_label",
    "is_non_standard_period",
    "submission_date",
    "revision_date",
    "pdf_url",
    "xbrl_url",
    "xbrl_file_name",
    "filing_id",
    "source_file",
]

LISTING_FILE_RE = re.compile(
    r"^CF-BRSR-equities-(?P<symbol>.+)-\d{2}-\d{2}-\d{4}-to-\d{2}-\d{2}-\d{4}\.csv$",
    re.IGNORECASE,
)

# Locale-independent month abbreviations for "%d-%b-%Y" dates.
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
)}  # fmt: skip

# Filings that NSE lists but whose XBRL file NSE does not serve (checked manually).
KNOWN_UNAVAILABLE: dict[str, str] = {
    "BRSR_1167401_29062024075519_WEB.xml": "M&M FY2023-24: listed, but NSE returns an error",
}


def filing_id_from_url(xbrl_url: str) -> str:
    """Return the deterministic filing id: SHA-256 hex digest of the (stripped) XBRL URL."""
    return hashlib.sha256(xbrl_url.strip().encode("utf-8")).hexdigest()


def normalise_header(header: str) -> str:
    """``'**XBRL \\n'`` -> ``'XBRL'``: strip whitespace and asterisks, collapse inner spaces."""
    return " ".join(header.strip().strip("*").split())


def parse_nse_date(value: str | None) -> date | None:
    """Parse ``'05-Oct-2026'``; ``'-'``, empty or None -> None. Raises ValueError otherwise."""
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "-"}:
        return None
    try:
        day, mon, year = text.split("-")
        return date(int(year), _MONTHS[mon.lower()], int(day))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unrecognised NSE date: {value!r}") from exc


def symbol_from_filename(name: str) -> str:
    """``CF-BRSR-equities-M&M-01-04-2023-to-08-10-2026.csv`` -> ``M&M``."""
    match = LISTING_FILE_RE.match(Path(name).name)
    if not match:
        raise ValueError(f"not an NSE BRSR listing file name: {name!r}")
    return match.group("symbol")


def read_listing_csv(path: Path, symbol: str | None = None) -> pd.DataFrame:
    """Read and normalise one listing CSV. ``symbol`` defaults to the one in the file name."""
    raw = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    raw.columns = [normalise_header(c) for c in raw.columns]
    missing = set(COLUMN_MAP) - set(raw.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    df = raw[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    df = df.apply(lambda col: col.str.strip())

    df["symbol"] = symbol or symbol_from_filename(path.name)
    df["fy_from"] = df["fy_from"].astype("Int64")
    df["fy_to"] = df["fy_to"].astype("Int64")
    df["reporting_year_label"] = df["fy_from"].astype(str) + "-" + df["fy_to"].astype(str)
    df["is_non_standard_period"] = (df["fy_to"] - df["fy_from"]) != 1
    df["submission_date"] = df["submission_date"].map(parse_nse_date)
    df["revision_date"] = df["revision_date"].map(parse_nse_date)
    df["xbrl_file_name"] = df["xbrl_url"].map(lambda u: u.rsplit("/", 1)[-1])
    df["filing_id"] = df["xbrl_url"].map(filing_id_from_url)
    df["source_file"] = path.name
    return df[LISTING_COLUMNS]


def load_listings(listing_dir: Path = config.LISTING_DIR) -> pd.DataFrame:
    """Read every listing CSV in ``listing_dir`` into one table, de-duplicated on ``xbrl_url``."""
    files = sorted(listing_dir.glob("*.csv"))
    if not files:
        return pd.DataFrame(columns=LISTING_COLUMNS)
    df = pd.concat([read_listing_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(subset="xbrl_url", keep="first")
    return df.sort_values(["symbol", "fy_from", "fy_to"], ignore_index=True)


def main() -> None:
    df = load_listings()
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.LISTING_PARQUET, index=False)
    print(
        f"listing: {len(df)} filings, {df['symbol'].nunique()} companies, "
        f"{int(df['is_non_standard_period'].sum())} non-standard periods "
        f"-> {config.display_path(config.LISTING_PARQUET)}"
    )


if __name__ == "__main__":
    main()
