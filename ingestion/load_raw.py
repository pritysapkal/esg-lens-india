"""Load the parsed Parquet tables into DuckDB as raw tables for a quick look.

Creates (or replaces) ``raw_filings``, ``raw_contexts``, ``raw_units``, ``raw_facts`` and
``raw_text_facts`` in the warehouse (``config.DUCKDB_PATH``), reading
``data/processed/parsed/<table>/reporting_year_label=*/*.parquet`` with hive partitioning so
``reporting_year_label`` becomes a column. No casting or cleaning - that is dbt staging's job.

CLI: ``python -m ingestion.load_raw``
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from ingestion import config
from ingestion.parse_xbrl import TABLES


def load_raw(
    parsed_dir: Path = config.PARSED_DIR, duckdb_path: Path = config.DUCKDB_PATH
) -> dict[str, int]:
    """Create ``raw_<table>`` for each parsed table; returns {table: row count}."""
    counts: dict[str, int] = {}
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(duckdb_path)) as con:
        for table in TABLES:
            files = sorted((parsed_dir / table).glob("*/*.parquet"))
            if not files:
                raise FileNotFoundError(
                    f"no Parquet under {config.display_path(parsed_dir / table)} - "
                    "run python -m ingestion.parse_xbrl first"
                )
            pattern = (parsed_dir / table).as_posix() + "/*/*.parquet"
            con.execute(
                f"create or replace table raw_{table} as "
                "select * from read_parquet(?, hive_partitioning = true, union_by_name = true)",
                [pattern],
            )
            counts[table] = con.execute(f"select count(*) from raw_{table}").fetchone()[0]
    return counts


def main() -> None:
    counts = load_raw()
    print(f"load_raw -> {config.display_path(config.DUCKDB_PATH)}")
    for table, n in counts.items():
        print(f"  raw_{table:<11} {n:>9,} rows")


if __name__ == "__main__":
    main()
