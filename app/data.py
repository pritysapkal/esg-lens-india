"""The only door to data for the Streamlit report card and the AI analyst.

Reads ONLY the public Parquet files in exports/public (the rpt_public_* models: values
ESG Lens India calculates, never filed values - docs/publication_policy.md). Every read goes
through `table()`, which accepts only a name from PUBLIC_TABLES and opens the file with Python's
`open`, so a test can watch every file the app touches (tests/test_app.py).
"""

from __future__ import annotations

import io
import os
from functools import cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = Path(os.getenv("ESG_PUBLIC_DIR") or ROOT / "exports" / "public")

PUBLIC_TABLES = (
    "rpt_public_company_year",
    "rpt_public_disclosure_quality",
    "rpt_public_group_metrics",
    "rpt_public_restatement_summary",
    "rpt_public_concentration",
    "rpt_public_company_percentile",
    "rpt_public_ghg_yoy",
)

DISCLAIMER = (
    "The Disclosure Quality Score is not an ESG rating, and nothing here is investment advice."
)
SOURCE_NOTE = (
    "Source: ESG Lens India, calculated from the companies' BRSR filings (XBRL) for FY2022-23 "
    "to FY2025-26. Only values we calculate are shown; filed values are not."
)


class NotPublic(ValueError):
    """A table that is not one of the public models was asked for."""


@cache
def table(name: str) -> pd.DataFrame:
    """One public table. Raises NotPublic for any other name."""
    if name not in PUBLIC_TABLES:
        raise NotPublic(f"{name} is not a public table")
    path = PUBLIC_DIR / f"{name}.parquet"
    with open(path, "rb") as fh:  # Python's open, so audit hooks see every read
        frame = pd.read_parquet(io.BytesIO(fh.read()))
    return frame


def available() -> bool:
    return all((PUBLIC_DIR / f"{name}.parquet").exists() for name in PUBLIC_TABLES)


def years() -> list[str]:
    return sorted(table("rpt_public_company_year")["fiscal_year_label"].dropna().unique())


def latest_year() -> str:
    return years()[-1]


def latest_final_year() -> str:
    """The latest year whose figures a later report could already confirm."""
    dqs = table("rpt_public_disclosure_quality")
    final = dqs.loc[~dqs["is_provisional"].astype(bool), "fiscal_year_label"]
    return sorted(final.unique())[-1]


def is_provisional(year: str) -> bool:
    return year == latest_year()


def provisional_note(year: str) -> str:
    if is_provisional(year):
        return (
            f"{year} is provisional: no later report has confirmed these figures yet, and "
            "they can still change."
        )
    return ""


def companies() -> pd.DataFrame:
    """One row per company: its latest name, symbol and groups."""
    frame = table("rpt_public_company_year").sort_values("fiscal_year_label")
    columns = ["isin", "symbol", "display_name", "peer_group", "sector_group", "ranking_group"]
    return frame.drop_duplicates("isin", keep="last")[columns].sort_values("display_name")


def group_row(group_type: str, group_value: str, year: str) -> pd.Series | None:
    groups = table("rpt_public_group_metrics")
    rows = groups[
        (groups["group_type"] == group_type)
        & (groups["group_value"] == group_value)
        & (groups["fiscal_year_label"] == year)
    ]
    return None if rows.empty else rows.iloc[0]


def withheld_label(reason: str | None) -> str:
    """How an empty group figure is shown."""
    reason = reason or ""
    if "fewer_than_5" in reason:
        return "n<5 (withheld)"
    if "not_yet_observable" in reason:
        return "not yet observable"
    return "-"
