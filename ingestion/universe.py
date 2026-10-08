"""Company universe: the official NIFTY 50 constituents list (niftyindices.com, saved manually)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ingestion import config


def snake_case(name: str) -> str:
    """``'ISIN Code'`` -> ``'isin_code'``."""
    return re.sub(r"[^0-9a-z]+", "_", name.strip().lower()).strip("_")


def load_universe(path: Path = config.UNIVERSE_CSV) -> pd.DataFrame:
    """Return the constituents with snake_case columns (company_name, industry, symbol, ...)."""
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df.columns = [snake_case(c) for c in df.columns]
    return df.apply(lambda col: col.str.strip())


def main() -> None:
    df = load_universe()
    print(f"universe: {len(df)} companies from {config.display_path(config.UNIVERSE_CSV)}")


if __name__ == "__main__":
    main()
