"""Run the SQL business analysis (Week 10) and save every result as a CSV file.

    python scripts/run_analysis.py                 # all questions
    python scripts/run_analysis.py --only q03      # one question
    python scripts/run_analysis.py --allow-empty   # do not fail on a result without rows

Each file in analysis/sql/ answers one business question with one or more queries on the gold
tables. A query is introduced by a comment line "-- result: <name>" and ends with a semicolon.
Results are written to data/processed/analysis/<file>__<name>.csv. That folder is local and
never committed: the results can hold raw filed values. Published findings are written up by
hand in docs/analysis_findings.md, with derived values only (docs/publication_policy.md).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "analysis" / "sql"
OUT_DIR = ROOT / "data" / "processed" / "analysis"
DEFAULT_DB = ROOT / "data" / "warehouse" / "esg_lens.duckdb"
RESULT_MARKER = re.compile(r"^-- result: (?P<name>[a-z0-9_]+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Query:
    """One query of a question file."""

    file: str  # e.g. q01_decarbonisation
    name: str  # e.g. ghg_intensity_by_sector
    sql: str

    @property
    def result_id(self) -> str:
        return f"{self.file}__{self.name}"


def load_queries(sql_dir: Path = SQL_DIR, only: str | None = None) -> list[Query]:
    """Read the question files and split them into their named queries."""
    queries: list[Query] = []
    for path in sorted(sql_dir.glob("q[0-9][0-9]_*.sql")):
        if only and not path.stem.startswith(only):
            continue
        text = path.read_text(encoding="utf-8")
        markers = list(RESULT_MARKER.finditer(text))
        if not markers:
            raise SystemExit(f"{path.name}: no '-- result: <name>' line found")
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            sql = text[marker.end() : end].strip().rstrip(";").strip()
            if ";" in sql:
                raise SystemExit(f"{path.name}: result {marker['name']} holds more than one query")
            queries.append(Query(path.stem, marker["name"], sql))
    return queries


def run_queries(con: duckdb.DuckDBPyConnection, queries: list[Query]) -> dict[str, object]:
    """Run every query and return its result as a pandas DataFrame, keyed by result id."""
    return {query.result_id: con.sql(query.sql).df() for query in queries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path(os.getenv("DUCKDB_PATH") or DEFAULT_DB))
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--only", help="run only the files that start with this, e.g. q03")
    parser.add_argument(
        "--allow-empty", action="store_true", help="a result without rows is not an error"
    )
    args = parser.parse_args(argv)

    if not args.db.exists():
        raise SystemExit(f"warehouse not found: {args.db} (run .\\scripts\\dev.ps1 dbt-build)")
    queries = load_queries(only=args.only)
    args.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.db), read_only=True)
    empty: list[str] = []
    try:
        for query in queries:
            try:
                frame = con.sql(query.sql).df()
            except duckdb.Error as exc:
                raise SystemExit(f"{query.result_id}: {exc}") from exc
            frame.to_csv(args.out / f"{query.result_id}.csv", index=False)
            print(f"{query.result_id:<62} {len(frame):>4} rows")
            if frame.empty:
                empty.append(query.result_id)
    finally:
        con.close()
    print(f"{len(queries)} results written to {args.out}")
    if empty and not args.allow_empty:
        print("no rows: " + ", ".join(empty))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
